"""SentimentAnalyzer must not fail on text that exceeds FinBERT's 512-token limit.

Regression: documents <=1500 chars (the analyzer's char cap) but >512 tokens
raised "The size of tensor a (N) must match the size of tensor b (512)" and
were stuck SENTIMENT_FAILED (2026-10-01, Adani Group run).

Fully offline: uses the real FinBERT *tokenizer* (from the local HF cache; test
is skipped if absent) with a tiny randomly-initialised BERT that has the same
512 position embeddings, so no weights are downloaded and no DB/Redis is touched.
"""
import pytest

transformers = pytest.importorskip("transformers")

from app.core import nlp_cache
from app.services.intelligence.sentiment_analyzer import SentimentAnalyzer

# Token-dense: numbers/URLs/symbols tokenize at ~1.7 chars/token.
DENSE_TEXT = (
    "Q3 revenue $4.2B (+12.5%) vs $3.7B; EBITDA 1,284.6M; see https://x.co/a1b2c3 #AI @adani "
    * 17
)[:1500]


@pytest.fixture(scope="module")
def tokenizer():
    try:
        return transformers.AutoTokenizer.from_pretrained("ProsusAI/finbert", local_files_only=True)
    except Exception as e:  # not cached on this machine
        pytest.skip(f"FinBERT tokenizer not available offline: {e}")


@pytest.fixture
def analyzer(tokenizer, monkeypatch):
    monkeypatch.setattr(nlp_cache, "get_cached", lambda key: None)
    monkeypatch.setattr(nlp_cache, "set_cached", lambda key, value: None)
    cfg = transformers.BertConfig(
        vocab_size=tokenizer.vocab_size, hidden_size=32, num_hidden_layers=1,
        num_attention_heads=2, intermediate_size=64, max_position_embeddings=512,
        num_labels=3,
        id2label={0: "positive", 1: "negative", 2: "neutral"},
        label2id={"positive": 0, "negative": 1, "neutral": 2},
    )
    model = transformers.BertForSequenceClassification(cfg).eval()
    sa = SentimentAnalyzer.__new__(SentimentAnalyzer)  # skip loading real FinBERT weights
    sa.use_mock = False
    sa.model_name = "ProsusAI/finbert"
    sa.model_version = "1.0"
    sa.sentiment_pipeline = transformers.pipeline(
        "sentiment-analysis", model=model, tokenizer=tokenizer, device=-1
    )
    return sa


def test_fixture_text_really_exceeds_512_tokens(tokenizer):
    # Guards against a vacuous test: the input must be <=1500 chars yet >512 tokens.
    assert len(DENSE_TEXT) <= 1500
    assert len(tokenizer(DENSE_TEXT)["input_ids"]) > 512


def test_analyze_text_handles_over_512_tokens(analyzer):
    result = analyzer.analyze_text(DENSE_TEXT)
    assert result["label"] in {"positive", "negative", "neutral"}
    assert 0.0 <= result["score"] <= 1.0


def test_analyze_batch_handles_over_512_tokens(analyzer):
    results = analyzer.analyze_batch([DENSE_TEXT, "Profit up."], batch_size=2)
    assert len(results) == 2
    assert all(r["label"] in {"positive", "negative", "neutral"} for r in results)


def test_short_text_result_unchanged_by_truncation_kwargs(analyzer):
    short = "Adani posts record quarterly profit."
    assert analyzer.analyze_text(short) == analyzer.sentiment_pipeline(short)[0]
