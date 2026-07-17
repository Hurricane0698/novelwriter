//! PyO3 boundary for the state-proto index kernel. Conversion glue only:
//! payload/build logic lives in `core`, zh bootstrap text helpers in `zh`.

mod core;
mod zh;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::pybacked::PyBackedStr;
use pyo3::types::{PyBytes, PyDict, PyTuple};
use rustc_hash::FxHashSet;

use crate::core::{
    assemble_payload_bytes, build_full as build_full_request, plan_update_result,
    update_incremental as update_incremental_request, BuildRequest, BuildResult, PayloadError,
    RequestChapter, RequestTarget, UpdatePlanResult, STATE_PROTO_PAYLOAD_FORMAT_VERSION,
};
use crate::zh::candidates::{
    collect_candidate_counts, release_zh_tokenizer, sort_candidate_counts,
    truncate_candidate_counts_topk, with_zh_tokenizer,
};
use crate::zh::normalize::{normalize_zh_chapter_strings, normalize_zh_variant_chars};

impl From<PayloadError> for PyErr {
    fn from(value: PayloadError) -> Self {
        PyValueError::new_err(value.to_string())
    }
}

fn common_word_set(common_words: Vec<PyBackedStr>) -> FxHashSet<String> {
    common_words
        .into_iter()
        .map(|word| word.to_string())
        .collect()
}

#[pyfunction]
fn payload_format_version() -> u32 {
    STATE_PROTO_PAYLOAD_FORMAT_VERSION
}

#[pyfunction]
fn tokenize_zh_text(py: Python<'_>, text: &str) -> PyResult<Vec<String>> {
    let source = text.to_owned();
    Ok(py.allow_threads(|| {
        with_zh_tokenizer(|tokenizer| {
            tokenizer
                .cut(&source, true)
                .into_iter()
                .map(str::to_owned)
                .collect()
        })
    }))
}

#[pyfunction]
fn count_zh_candidates(
    py: Python<'_>,
    chapters: Vec<PyBackedStr>,
    common_words: Vec<PyBackedStr>,
    max_batch_chars: usize,
) -> PyResult<Vec<(String, usize)>> {
    Ok(py.allow_threads(|| {
        let common_word_set = common_word_set(common_words);
        let mut counts = collect_candidate_counts(
            normalize_zh_chapter_strings(chapters),
            &common_word_set,
            max_batch_chars,
        );
        sort_candidate_counts(&mut counts);
        release_zh_tokenizer();
        counts
    }))
}

#[pyfunction]
fn count_zh_candidates_topk(
    py: Python<'_>,
    chapters: Vec<PyBackedStr>,
    common_words: Vec<PyBackedStr>,
    max_batch_chars: usize,
    limit: usize,
) -> PyResult<Vec<(String, usize)>> {
    Ok(py.allow_threads(|| {
        let common_word_set = common_word_set(common_words);
        let mut counts = collect_candidate_counts(
            normalize_zh_chapter_strings(chapters),
            &common_word_set,
            max_batch_chars,
        );
        truncate_candidate_counts_topk(&mut counts, limit);
        release_zh_tokenizer();
        counts
    }))
}

fn summarize_zh_windows_compact_impl(
    chapters: Vec<PyBackedStr>,
    shortlisted_candidates: Vec<PyBackedStr>,
    window_size: usize,
    window_step: usize,
    threshold: usize,
) -> Result<zh::windows::CompactWindowItems, String> {
    let normalized_chapters = normalize_zh_chapter_strings(chapters);
    let normalized_candidates = shortlisted_candidates
        .into_iter()
        .map(|candidate| normalize_zh_variant_chars(candidate.as_ref()).into_owned())
        .collect();
    let (candidate_names, importance_counts, pair_counts) = zh::windows::summarize_window_counts(
        normalized_chapters,
        normalized_candidates,
        window_size,
        window_step,
    )?;
    Ok(zh::windows::compact_window_items(
        candidate_names,
        importance_counts,
        pair_counts,
        threshold,
    ))
}

/// `(named importance items, named co-occurrence pair items)`.
type NamedWindowSummary = (Vec<(String, usize)>, Vec<(String, String, usize)>);

#[pyfunction]
fn summarize_zh_windows(
    py: Python<'_>,
    chapters: Vec<PyBackedStr>,
    shortlisted_candidates: Vec<PyBackedStr>,
    window_size: usize,
    window_step: usize,
    threshold: usize,
) -> PyResult<NamedWindowSummary> {
    py.allow_threads(|| {
        let (candidate_names, importance_items, pair_items) = summarize_zh_windows_compact_impl(
            chapters,
            shortlisted_candidates,
            window_size,
            window_step,
            threshold,
        )?;
        let importance = importance_items
            .into_iter()
            .map(|(candidate_id, count)| (candidate_names[candidate_id].clone(), count))
            .collect();
        let pairs = pair_items
            .into_iter()
            .map(|(left_id, right_id, count)| {
                (
                    candidate_names[left_id].clone(),
                    candidate_names[right_id].clone(),
                    count,
                )
            })
            .collect();
        Ok((importance, pairs))
    })
    .map_err(|err: String| PyValueError::new_err(err))
}

#[pyfunction]
fn summarize_zh_windows_compact(
    py: Python<'_>,
    chapters: Vec<PyBackedStr>,
    shortlisted_candidates: Vec<PyBackedStr>,
    window_size: usize,
    window_step: usize,
    threshold: usize,
) -> PyResult<zh::windows::CompactWindowItems> {
    py.allow_threads(|| {
        summarize_zh_windows_compact_impl(
            chapters,
            shortlisted_candidates,
            window_size,
            window_step,
            threshold,
        )
    })
    .map_err(PyValueError::new_err)
}

#[pyfunction]
fn build_zh_block_refinement_inputs_compact(
    py: Python<'_>,
    chapters: Vec<PyBackedStr>,
    common_words: Vec<PyBackedStr>,
    limit: usize,
) -> PyResult<zh::blocks::CompactRefinementOutput> {
    py.allow_threads(|| {
        let common_word_set = common_word_set(common_words);
        zh::blocks::build_block_refinement_inputs(
            normalize_zh_chapter_strings(chapters),
            &common_word_set,
            limit,
        )
    })
    .map_err(PyValueError::new_err)
}

#[pyfunction]
fn plan_update(
    py: Python<'_>,
    existing_payload: Option<&[u8]>,
    requested_language: Option<String>,
    chapters: Vec<(i64, String, String)>,
    targets: Vec<(String, String, String, Vec<String>)>,
) -> PyResult<Py<PyDict>> {
    let request = build_request(requested_language, chapters, targets);
    let existing_payload = existing_payload.map(|payload| payload.to_vec());
    let result = py.allow_threads(|| plan_update_result(existing_payload.as_deref(), &request));
    update_plan_dict(py, &result)
}

#[pyfunction]
fn assemble_payload<'py>(
    py: Python<'py>,
    request_json: &[u8],
    chapter_shards_json: &[u8],
    existing_payload: Option<&[u8]>,
) -> PyResult<Py<PyTuple>> {
    let request_json = request_json.to_vec();
    let chapter_shards_json = chapter_shards_json.to_vec();
    let existing_payload = existing_payload.map(|payload| payload.to_vec());
    let (payload_bytes, result_bytes) = py.allow_threads(|| {
        assemble_payload_bytes(
            &request_json,
            &chapter_shards_json,
            existing_payload.as_deref(),
        )
    })?;
    bytes_pair_tuple(py, &payload_bytes, &result_bytes)
}

#[pyfunction]
fn build_full_structured<'py>(
    py: Python<'py>,
    requested_language: Option<String>,
    chapters: Vec<(i64, String, String)>,
    targets: Vec<(String, String, String, Vec<String>)>,
) -> PyResult<Py<PyTuple>> {
    let request = build_request(requested_language, chapters, targets);
    let (payload_bytes, result) = py.allow_threads(|| build_full_request(request))?;
    payload_result_tuple(py, &payload_bytes, &result)
}

#[pyfunction]
fn update_incremental_structured<'py>(
    py: Python<'py>,
    existing_payload: &[u8],
    requested_language: Option<String>,
    chapters: Vec<(i64, String, String)>,
    targets: Vec<(String, String, String, Vec<String>)>,
) -> PyResult<Py<PyTuple>> {
    let request = build_request(requested_language, chapters, targets);
    let existing_payload = existing_payload.to_vec();
    let (payload_bytes, result) =
        py.allow_threads(|| update_incremental_request(&existing_payload, request))?;
    payload_result_tuple(py, &payload_bytes, &result)
}

fn build_request(
    requested_language: Option<String>,
    chapters: Vec<(i64, String, String)>,
    targets: Vec<(String, String, String, Vec<String>)>,
) -> BuildRequest {
    BuildRequest {
        format_version: STATE_PROTO_PAYLOAD_FORMAT_VERSION,
        requested_language,
        chapters: chapters
            .into_iter()
            .map(|(chapter_id, text, signature)| RequestChapter {
                chapter_id,
                text,
                signature: Some(signature),
            })
            .collect(),
        targets: targets
            .into_iter()
            .map(|(id, canonical_name, kind, aliases)| RequestTarget {
                id,
                canonical_name,
                kind,
                aliases,
            })
            .collect(),
    }
}

fn bytes_pair_tuple(py: Python<'_>, payload: &[u8], result: &[u8]) -> PyResult<Py<PyTuple>> {
    let tuple = PyTuple::new(
        py,
        [
            PyBytes::new(py, payload).into_any(),
            PyBytes::new(py, result).into_any(),
        ],
    )?;
    Ok(tuple.unbind())
}

fn payload_result_tuple(
    py: Python<'_>,
    payload: &[u8],
    result: &BuildResult,
) -> PyResult<Py<PyTuple>> {
    let tuple = PyTuple::new(
        py,
        [
            PyBytes::new(py, payload).into_any(),
            build_result_dict(py, result)?.into_bound(py).into_any(),
        ],
    )?;
    Ok(tuple.unbind())
}

fn update_plan_dict(py: Python<'_>, result: &UpdatePlanResult) -> PyResult<Py<PyDict>> {
    let data = PyDict::new(py);
    data.set_item("mode", result.mode.as_str())?;
    data.set_item("supported_incremental", result.supported_incremental)?;
    data.set_item(
        "existing_payload_compatible",
        result.existing_payload_compatible,
    )?;
    data.set_item("target_catalog_changed", result.target_catalog_changed)?;
    data.set_item("dirty_chapter_ids", result.dirty_chapter_ids.clone())?;
    data.set_item("fallback_reason", result.fallback_reason.clone())?;
    data.set_item("no_changes", result.no_changes)?;
    Ok(data.unbind())
}

fn build_result_dict(py: Python<'_>, result: &BuildResult) -> PyResult<Py<PyDict>> {
    let data = PyDict::new(py);
    data.set_item("payload_bytes", result.payload_bytes)?;
    data.set_item("chapter_count", result.chapter_count)?;
    data.set_item("chapter_chars", result.chapter_chars)?;
    data.set_item("target_count", result.target_count)?;
    data.set_item("segment_count", result.segment_count)?;
    data.set_item("mention_posting_count", result.mention_posting_count)?;
    data.set_item("claim_atom_count", result.claim_atom_count)?;
    data.set_item("coverage_rep_count", result.coverage_rep_count)?;
    data.set_item("segmentation_ms", result.segmentation_ms)?;
    data.set_item("mention_ms", result.mention_ms)?;
    data.set_item("claim_ms", result.claim_ms)?;
    data.set_item("coverage_ms", result.coverage_ms)?;
    data.set_item("serialize_ms", result.serialize_ms)?;
    data.set_item("duration_ms", result.duration_ms)?;
    data.set_item("plan_mode", result.plan_mode.as_str())?;
    data.set_item("incremental_applied", result.incremental_applied)?;
    data.set_item("rebuilt_chapter_count", result.rebuilt_chapter_count)?;
    data.set_item("reused_chapter_count", result.reused_chapter_count)?;
    data.set_item("fallback_reason", result.fallback_reason.clone())?;
    Ok(data.unbind())
}

#[pymodule]
fn _novwr_state_proto(_py: Python<'_>, module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(payload_format_version, module)?)?;
    module.add_function(wrap_pyfunction!(tokenize_zh_text, module)?)?;
    module.add_function(wrap_pyfunction!(count_zh_candidates, module)?)?;
    module.add_function(wrap_pyfunction!(count_zh_candidates_topk, module)?)?;
    module.add_function(wrap_pyfunction!(summarize_zh_windows, module)?)?;
    module.add_function(wrap_pyfunction!(summarize_zh_windows_compact, module)?)?;
    module.add_function(wrap_pyfunction!(
        build_zh_block_refinement_inputs_compact,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(plan_update, module)?)?;
    module.add_function(wrap_pyfunction!(assemble_payload, module)?)?;
    module.add_function(wrap_pyfunction!(build_full_structured, module)?)?;
    module.add_function(wrap_pyfunction!(update_incremental_structured, module)?)?;
    Ok(())
}
