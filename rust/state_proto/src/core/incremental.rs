use super::claim::build_claim_atoms;
use super::mention::build_mention_postings;
use super::payload::prepare_payload;
use super::segment::{
    normalize_chapter_text, segment_chapter_text, segment_chapter_text_without_index,
};
use super::*;

fn chapter_ids_match_prefix(existing: &[ChapterShard], request: &[RequestChapter]) -> bool {
    if request.len() < existing.len() {
        return false;
    }
    existing
        .iter()
        .zip(request.iter())
        .all(|(existing_chapter, request_chapter)| {
            existing_chapter.chapter_id == request_chapter.chapter_id
        })
}

fn determine_dirty_chapter_ids(existing: &[ChapterShard], request: &[RequestChapter]) -> Vec<i64> {
    let existing_by_id: HashMap<i64, &ChapterShard> = existing
        .iter()
        .map(|chapter| (chapter.chapter_id, chapter))
        .collect();

    request
        .iter()
        .filter_map(|chapter| match existing_by_id.get(&chapter.chapter_id) {
            None => Some(chapter.chapter_id),
            Some(existing_chapter) => {
                if existing_chapter.signature != chapter.signature {
                    Some(chapter.chapter_id)
                } else {
                    None
                }
            }
        })
        .collect()
}

fn full_rebuild_plan(
    request: &BuildRequest,
    existing_payload_compatible: bool,
    target_catalog_changed: bool,
    fallback_reason: &str,
) -> UpdatePlanResult {
    UpdatePlanResult {
        mode: "full".to_owned(),
        supported_incremental: false,
        existing_payload_compatible,
        target_catalog_changed,
        dirty_chapter_ids: request
            .chapters
            .iter()
            .map(|chapter| chapter.chapter_id)
            .collect(),
        fallback_reason: Some(fallback_reason.to_owned()),
        no_changes: false,
    }
}

pub fn plan_update_result(
    existing_payload: Option<&[u8]>,
    request: &BuildRequest,
) -> UpdatePlanResult {
    let Some(payload_bytes) = existing_payload else {
        return full_rebuild_plan(request, false, false, "missing_existing_payload");
    };
    let Ok(existing) = decode_payload(payload_bytes) else {
        return full_rebuild_plan(request, false, false, "legacy_payload");
    };

    if existing.targets != request_targets_as_wire(&request.targets) {
        return full_rebuild_plan(request, true, true, "target_catalog_changed");
    }
    if !chapter_ids_match_prefix(&existing.chapters, &request.chapters) {
        return full_rebuild_plan(request, true, false, "unsupported_structure_change");
    }

    let dirty_chapter_ids = determine_dirty_chapter_ids(&existing.chapters, &request.chapters);
    let no_changes = dirty_chapter_ids.is_empty();
    UpdatePlanResult {
        mode: if no_changes {
            "reuse_existing".to_owned()
        } else if dirty_chapter_ids.len() == request.chapters.len() {
            "full".to_owned()
        } else {
            "incremental".to_owned()
        },
        supported_incremental: true,
        existing_payload_compatible: true,
        target_catalog_changed: false,
        dirty_chapter_ids,
        fallback_reason: None,
        no_changes,
    }
}

fn build_request_shards(
    request: &BuildRequest,
    dirty_only: Option<&HashSet<i64>>,
    context: &BuildContext,
) -> Result<(Vec<ChapterShardData>, StageStats), PayloadError> {
    let mut stats = StageStats::default();
    let mut shards = Vec::new();
    let has_targets = !context.alias_entries.is_empty();
    for (index, chapter) in request.chapters.iter().enumerate() {
        if let Some(dirty) = dirty_only {
            if !dirty.contains(&chapter.chapter_id) {
                continue;
            }
        }
        let chapter_number = (index + 1) as i64;
        let normalized = normalize_chapter_text(&chapter.text);
        if !has_targets {
            let segmentation_started = Instant::now();
            let segments =
                segment_chapter_text_without_index(chapter.chapter_id, chapter_number, &normalized);
            stats.segmentation_ms +=
                round_ms(segmentation_started.elapsed().as_secs_f64() * 1000.0);
            shards.push(ChapterShardData {
                chapter_id: chapter.chapter_id,
                chapter_number,
                signature: chapter.signature.clone(),
                segments,
                mentions: Vec::new(),
                claims: Vec::new(),
            });
            continue;
        }
        let indexed = IndexedText::new(normalized);

        let segmentation_started = Instant::now();
        let segments = segment_chapter_text(chapter.chapter_id, chapter_number, &indexed);
        stats.segmentation_ms += round_ms(segmentation_started.elapsed().as_secs_f64() * 1000.0);

        let mention_started = Instant::now();
        let (mentions, grouped_matches) = build_mention_postings(&segments, &indexed, context);
        stats.mention_ms += round_ms(mention_started.elapsed().as_secs_f64() * 1000.0);

        let claim_started = Instant::now();
        let claims = build_claim_atoms(
            chapter.chapter_id,
            &segments,
            &indexed,
            context,
            &grouped_matches,
        )?;
        stats.claim_ms += round_ms(claim_started.elapsed().as_secs_f64() * 1000.0);

        shards.push(ChapterShardData {
            chapter_id: chapter.chapter_id,
            chapter_number,
            signature: chapter.signature.clone(),
            segments,
            mentions,
            claims,
        });
    }
    Ok((shards, stats))
}

pub fn build_full(request: BuildRequest) -> Result<(Vec<u8>, BuildResult), PayloadError> {
    let started = Instant::now();
    let chapter_chars: usize = request
        .chapters
        .iter()
        .map(|chapter| chapter.text.chars().count())
        .sum();
    let language = resolve_language(request.requested_language.as_deref());
    let context = build_context(&request.targets, &language)?;
    let (shards, stats) = build_request_shards(&request, None, &context)?;

    let coverage_started = Instant::now();
    let (payload, counts) = prepare_payload(request.clone(), shards, None)?;
    let coverage_ms = round_ms(coverage_started.elapsed().as_secs_f64() * 1000.0);

    let serialize_started = Instant::now();
    let payload_bytes = serialize_payload(&payload)?;
    let serialize_ms = round_ms(serialize_started.elapsed().as_secs_f64() * 1000.0);

    let result = BuildResult {
        payload_bytes: payload_bytes.len(),
        chapter_count: request.chapters.len(),
        chapter_chars,
        target_count: payload.targets.len(),
        segment_count: counts.segment_count,
        mention_posting_count: counts.mention_posting_count,
        claim_atom_count: counts.claim_atom_count,
        coverage_rep_count: counts.coverage_rep_count,
        segmentation_ms: stats.segmentation_ms,
        mention_ms: stats.mention_ms,
        claim_ms: stats.claim_ms,
        coverage_ms,
        serialize_ms,
        duration_ms: round_ms(started.elapsed().as_secs_f64() * 1000.0),
        plan_mode: "full".to_owned(),
        incremental_applied: false,
        rebuilt_chapter_count: request.chapters.len(),
        reused_chapter_count: 0,
        fallback_reason: None,
    };
    Ok((payload_bytes, result))
}

pub fn update_incremental(
    existing_payload: &[u8],
    request: BuildRequest,
) -> Result<(Vec<u8>, BuildResult), PayloadError> {
    let started = Instant::now();
    let chapter_chars: usize = request
        .chapters
        .iter()
        .map(|chapter| chapter.text.chars().count())
        .sum();
    let plan = plan_update_result(Some(existing_payload), &request);

    if plan.mode == "reuse_existing" {
        let payload = decode_payload(existing_payload)?;
        let (target_count, segment_count, mention_count, claim_count, coverage_count) =
            count_payload(&payload);
        let result = BuildResult {
            payload_bytes: existing_payload.len(),
            chapter_count: request.chapters.len(),
            chapter_chars,
            target_count,
            segment_count,
            mention_posting_count: mention_count,
            claim_atom_count: claim_count,
            coverage_rep_count: coverage_count,
            segmentation_ms: 0.0,
            mention_ms: 0.0,
            claim_ms: 0.0,
            coverage_ms: 0.0,
            serialize_ms: 0.0,
            duration_ms: round_ms(started.elapsed().as_secs_f64() * 1000.0),
            plan_mode: plan.mode,
            incremental_applied: false,
            rebuilt_chapter_count: 0,
            reused_chapter_count: request.chapters.len(),
            fallback_reason: plan.fallback_reason,
        };
        return Ok((existing_payload.to_vec(), result));
    }

    let language = resolve_language(request.requested_language.as_deref());
    let context = build_context(&request.targets, &language)?;
    let dirty_ids: HashSet<i64> = plan.dirty_chapter_ids.iter().copied().collect();
    let dirty_filter = if plan.mode == "incremental" {
        Some(&dirty_ids)
    } else {
        None
    };
    let (shards, stats) = build_request_shards(&request, dirty_filter, &context)?;
    let existing = if plan.mode == "incremental" {
        Some(decode_payload(existing_payload)?)
    } else {
        None
    };

    let coverage_started = Instant::now();
    let (payload, counts) = prepare_payload(request.clone(), shards, existing)?;
    let coverage_ms = round_ms(coverage_started.elapsed().as_secs_f64() * 1000.0);

    let serialize_started = Instant::now();
    let payload_bytes = serialize_payload(&payload)?;
    let serialize_ms = round_ms(serialize_started.elapsed().as_secs_f64() * 1000.0);

    let result = BuildResult {
        payload_bytes: payload_bytes.len(),
        chapter_count: request.chapters.len(),
        chapter_chars,
        target_count: payload.targets.len(),
        segment_count: counts.segment_count,
        mention_posting_count: counts.mention_posting_count,
        claim_atom_count: counts.claim_atom_count,
        coverage_rep_count: counts.coverage_rep_count,
        segmentation_ms: stats.segmentation_ms,
        mention_ms: stats.mention_ms,
        claim_ms: stats.claim_ms,
        coverage_ms,
        serialize_ms,
        duration_ms: round_ms(started.elapsed().as_secs_f64() * 1000.0),
        plan_mode: plan.mode,
        incremental_applied: counts.incremental_applied,
        rebuilt_chapter_count: counts.rebuilt_chapter_count,
        reused_chapter_count: counts.reused_chapter_count,
        fallback_reason: plan.fallback_reason,
    };
    Ok((payload_bytes, result))
}

pub fn assemble_payload_bytes(
    request_json: &[u8],
    chapter_shards_json: &[u8],
    existing_payload: Option<&[u8]>,
) -> Result<(Vec<u8>, Vec<u8>), PayloadError> {
    let request = decode_request(request_json)?;
    let chapter_shards: Vec<ChapterShard> = serde_json::from_slice(chapter_shards_json)
        .map_err(|err| PayloadError::InvalidRequest(err.to_string()))?;
    let provided: Vec<ChapterShardData> = chapter_shards
        .iter()
        .map(ChapterShardData::from_wire)
        .collect();
    let existing = existing_payload.map(decode_payload).transpose()?;
    let (payload, counts) = prepare_payload(request, provided, existing)?;
    let payload_bytes = serialize_payload(&payload)?;
    let result = AssembleResult {
        payload_bytes: payload_bytes.len(),
        chapter_count: payload.chapters.len(),
        target_count: payload.targets.len(),
        segment_count: counts.segment_count,
        mention_posting_count: counts.mention_posting_count,
        claim_atom_count: counts.claim_atom_count,
        coverage_rep_count: counts.coverage_rep_count,
        rebuilt_chapter_count: counts.rebuilt_chapter_count,
        reused_chapter_count: counts.reused_chapter_count,
        incremental_applied: counts.incremental_applied,
    };
    let result_bytes =
        serde_json::to_vec(&result).map_err(|err| PayloadError::InvalidPayload(err.to_string()))?;
    Ok((payload_bytes, result_bytes))
}
