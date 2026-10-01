"""RuntimeError during per-document sentiment processing must be retried, and a
failed retry must end in a persisted terminal FAILED (never stuck RETRYING).

No DB/Redis/model: the processor's single-document step and the state machine's
persistence are patched.
"""
from unittest import mock

import pytest

from app.services.intelligence import sentiment_batch_processor as sbp
from app.services.intelligence.sentiment_batch_processor import (
    HardenedSentimentProcessor,
    SentimentDocumentResult,
    SentimentProcessingState as S,
    SentimentRetryConfig,
)


def test_runtime_error_is_not_permanent():
    cfg = SentimentRetryConfig()
    assert not cfg.is_permanent_failure("RuntimeError", "CPU allocator: can't allocate memory")


@pytest.mark.parametrize("exc", ["ValueError", "AttributeError", "UnicodeDecodeError"])
def test_other_permanent_patterns_unchanged(exc):
    assert SentimentRetryConfig().is_permanent_failure(exc, "boom")


def _failed(reason="RuntimeError: oom"):
    return SentimentDocumentResult(
        document_id="d", state=S.FAILED, failure_reason=reason, exception_type="RuntimeError"
    )


def _proc():
    return HardenedSentimentProcessor(analyzer_instance=object())


def test_runtime_error_retries_once_then_persists_failed():
    proc = _proc()
    with mock.patch.object(proc, "_process_single_document_in_transaction",
                           side_effect=[_failed(), _failed()]) as single, \
         mock.patch.object(sbp.SentimentDocumentStateMachine, "transition_and_commit") as persist, \
         mock.patch.object(sbp.time, "sleep"):
        result = proc._process_with_retry("d", "run", "batch", "c", 0, mock.MagicMock())
    assert single.call_count == 2                      # original attempt + one retry
    assert result.state == S.FAILED
    states = [c.args[1] for c in persist.call_args_list]
    assert states == [S.RETRYING, S.FAILED]            # not left stuck in RETRYING


def test_transient_failure_then_success_does_not_persist_failed():
    proc = _proc()
    ok = SentimentDocumentResult(document_id="d", state=S.COMPLETE)
    with mock.patch.object(proc, "_process_single_document_in_transaction",
                           side_effect=[_failed(), ok]), \
         mock.patch.object(sbp.SentimentDocumentStateMachine, "transition_and_commit") as persist, \
         mock.patch.object(sbp.time, "sleep"):
        result = proc._process_with_retry("d", "run", "batch", "c", 0, mock.MagicMock())
    assert result.state == S.COMPLETE
    assert [c.args[1] for c in persist.call_args_list] == [S.RETRYING]


def test_permanent_error_still_fails_without_retry():
    proc = _proc()
    bad = SentimentDocumentResult(document_id="d", state=S.FAILED,
                                  failure_reason="bad", exception_type="ValueError")
    with mock.patch.object(proc, "_process_single_document_in_transaction", return_value=bad) as single, \
         mock.patch.object(sbp.SentimentDocumentStateMachine, "transition_and_commit") as persist:
        proc._process_with_retry("d", "run", "batch", "c", 0, mock.MagicMock())
    assert single.call_count == 1
    assert [c.args[1] for c in persist.call_args_list] == [S.FAILED]
