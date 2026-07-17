use super::*;

pub(crate) fn prepare_payload(
    request: BuildRequest,
    provided_shards: Vec<ChapterShardData>,
    existing_payload: Option<PayloadWire>,
) -> Result<(PayloadWire, PayloadCounts), PayloadError> {
    let request_targets = request_targets_as_wire(&request.targets);

    let mut merged_by_id: HashMap<i64, ChapterShardData> = HashMap::new();
    if let Some(existing) = existing_payload.as_ref() {
        for chapter in &existing.chapters {
            merged_by_id.insert(chapter.chapter_id, ChapterShardData::from_wire(chapter));
        }
    }

    let rebuilt_ids: HashSet<i64> = provided_shards
        .iter()
        .map(|shard| shard.chapter_id)
        .collect();
    for mut shard in provided_shards {
        shard.segments.sort_by_key(|segment| segment.segment_id);
        shard
            .claims
            .sort_by_key(|claim| (claim.segment_id, claim.anchor_offset, claim.claim_id));
        merged_by_id.insert(shard.chapter_id, shard);
    }

    let mut chapters: Vec<ChapterShardData> = Vec::with_capacity(request.chapters.len());
    let mut reused_chapter_count = 0usize;
    for (index, request_chapter) in request.chapters.iter().enumerate() {
        let mut shard = merged_by_id
            .remove(&request_chapter.chapter_id)
            .ok_or_else(|| {
                PayloadError::InvalidPayload(format!(
                    "missing shard for chapter_id={} during assembly",
                    request_chapter.chapter_id
                ))
            })?;
        let chapter_number = (index + 1) as i64;
        let was_rebuilt = rebuilt_ids.contains(&request_chapter.chapter_id);
        if existing_payload.is_some()
            && !was_rebuilt
            && request_chapter.signature == shard.signature
        {
            reused_chapter_count += 1;
        }
        shard.chapter_number = chapter_number;
        shard.signature = request_chapter.signature.clone();
        for segment in shard.segments.iter_mut() {
            segment.chapter_id = request_chapter.chapter_id;
            segment.chapter_number = chapter_number;
        }
        for claim in shard.claims.iter_mut() {
            claim.chapter_number = chapter_number;
        }
        chapters.push(shard);
    }

    assign_progress_buckets(&mut chapters);
    let coverage = rebuild_coverage(&chapters);

    let segment_count = chapters.iter().map(|chapter| chapter.segments.len()).sum();
    let mention_posting_count = chapters.iter().map(|chapter| chapter.mentions.len()).sum();
    let claim_atom_count = chapters.iter().map(|chapter| chapter.claims.len()).sum();
    let coverage_rep_count = coverage.len();

    let payload = PayloadWire {
        kind: STATE_PROTO_PAYLOAD_KIND.to_owned(),
        v: STATE_PROTO_PAYLOAD_FORMAT_VERSION,
        language: resolve_language(request.requested_language.as_deref()),
        targets: request_targets,
        chapters: chapters.iter().map(ChapterShardData::to_wire).collect(),
        coverage: coverage.iter().map(CoverageData::to_row).collect(),
    };
    let counts = PayloadCounts {
        segment_count,
        mention_posting_count,
        claim_atom_count,
        coverage_rep_count,
        rebuilt_chapter_count: rebuilt_ids.len(),
        reused_chapter_count,
        incremental_applied: existing_payload.is_some()
            && !rebuilt_ids.is_empty()
            && rebuilt_ids.len() < request.chapters.len(),
    };
    Ok((payload, counts))
}

fn assign_progress_buckets(chapters: &mut [ChapterShardData]) {
    let total: usize = chapters.iter().map(|chapter| chapter.segments.len()).sum();
    if total == 0 {
        return;
    }
    let mut seen = 0usize;
    for chapter in chapters.iter_mut() {
        for segment in chapter.segments.iter_mut() {
            let bucket = (((seen as f64) / (total as f64)) * (DEFAULT_PROGRESS_BUCKETS as f64))
                .floor() as i64;
            segment.progress_bucket = bucket.clamp(0, DEFAULT_PROGRESS_BUCKETS - 1);
            seen += 1;
        }
    }
}

fn rebuild_coverage(chapters: &[ChapterShardData]) -> Vec<CoverageData> {
    let segments_by_id: HashMap<i64, &SegmentData> = chapters
        .iter()
        .flat_map(|chapter| {
            chapter
                .segments
                .iter()
                .map(|segment| (segment.segment_id, segment))
        })
        .collect();
    let mut best_by_target_bucket: BTreeMap<(String, i64), MentionData> = BTreeMap::new();
    for mention in chapters.iter().flat_map(|chapter| chapter.mentions.iter()) {
        let Some(segment) = segments_by_id.get(&mention.segment_id) else {
            continue;
        };
        let key = (mention.target_id.clone(), segment.progress_bucket);
        let should_replace = match best_by_target_bucket.get(&key) {
            None => true,
            Some(existing) => existing.mention_score < mention.mention_score,
        };
        if should_replace {
            best_by_target_bucket.insert(key, mention.clone());
        }
    }
    best_by_target_bucket
        .into_iter()
        .map(|((target_id, bucket_id), mention)| CoverageData {
            target_id,
            bucket_id,
            segment_id: mention.segment_id,
            rep_score: mention.mention_score,
        })
        .collect()
}
