"""
Unit tests for chart_analyst.py.

All tests mock the Anthropic API so no real network calls are made
and no API key is required.
"""
import pytest

from chart_analyst import analyse_chart, _cache


# ── Cache auto-clear ──────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the in-memory cache before and after every test."""
    _cache.clear()
    yield
    _cache.clear()


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_summary_stats():
    return {
        "total_return_pct":      24.5,
        "annualised_return_pct": 24.5,
        "volatility_pct":        18.3,
        "sharpe_ratio":          1.34,
        "max_drawdown_pct":     -12.1,
        "best_day_pct":          4.2,
        "worst_day_pct":        -3.8,
        "start_date":           "2023-01-02",
        "end_date":             "2023-12-29",
    }


@pytest.fixture
def mock_anthropic(mocker):
    """Patch anthropic.Anthropic so no real API calls are made.

    Returns the mock_client so tests can inspect call_args and
    override return values.
    """
    mock_message = mocker.MagicMock()
    mock_message.content = [
        mocker.MagicMock(
            text=(
                "AAPL delivered strong performance over the period. "
                "The candlestick chart shows a clear uptrend with "
                "brief consolidation in Q3."
            )
        )
    ]
    mock_client = mocker.MagicMock()
    mock_client.messages.create.return_value = mock_message

    mocker.patch("anthropic.Anthropic", return_value=mock_client)
    return mock_client


# ── API call behaviour ────────────────────────────────────────────────────────

@pytest.mark.unit
class TestAnalyseChart:

    def test_returns_non_empty_string(
        self, mock_anthropic, sample_summary_stats
    ):
        result = analyse_chart(
            chart_type="candlestick", symbol="AAPL",
            name="Apple Inc.", summary_stats=sample_summary_stats,
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_calls_anthropic_with_correct_model(
        self, mock_anthropic, sample_summary_stats
    ):
        analyse_chart(
            chart_type="candlestick", symbol="AAPL",
            name="Apple Inc.", summary_stats=sample_summary_stats,
        )
        kwargs = mock_anthropic.messages.create.call_args.kwargs
        assert kwargs["model"] == "claude-haiku-4-5"

    def test_calls_anthropic_with_max_tokens_150(
        self, mock_anthropic, sample_summary_stats
    ):
        analyse_chart(
            chart_type="price_ma", symbol="AAPL",
            name="Apple Inc.", summary_stats=sample_summary_stats,
        )
        kwargs = mock_anthropic.messages.create.call_args.kwargs
        assert kwargs["max_tokens"] == 150

    def test_prompt_includes_symbol(
        self, mock_anthropic, sample_summary_stats
    ):
        analyse_chart(
            chart_type="drawdown", symbol="TSLA",
            name="Tesla Inc.", summary_stats=sample_summary_stats,
        )
        user_content = (
            mock_anthropic.messages.create.call_args.kwargs["messages"][0]["content"]
        )
        assert "TSLA" in user_content or "Tesla" in user_content

    def test_prompt_includes_total_return_value(
        self, mock_anthropic, sample_summary_stats
    ):
        """The prompt must include the actual stat values so the model
        can reference concrete numbers."""
        analyse_chart(
            chart_type="cumulative_return", symbol="AAPL",
            name="Apple Inc.", summary_stats=sample_summary_stats,
        )
        user_content = (
            mock_anthropic.messages.create.call_args.kwargs["messages"][0]["content"]
        )
        assert "24.5" in user_content  # total_return_pct value

    def test_system_prompt_is_present(
        self, mock_anthropic, sample_summary_stats
    ):
        analyse_chart(
            chart_type="candlestick", symbol="AAPL",
            name="Apple Inc.", summary_stats=sample_summary_stats,
        )
        kwargs = mock_anthropic.messages.create.call_args.kwargs
        assert "system" in kwargs
        assert len(kwargs["system"]) > 0

    def test_chart_context_keywords_appear_in_prompt(
        self, mock_anthropic, sample_summary_stats
    ):
        """Each chart type must embed its context keyword in the user prompt."""
        context_keywords = {
            "candlestick":       "candlestick",
            "price_ma":          "moving average",
            "cumulative_return": "cumulative",
            "drawdown":          "drawdown",
            "monthly_returns":   "monthly",
        }
        for chart_type, keyword in context_keywords.items():
            _cache.clear()
            analyse_chart(
                chart_type=chart_type, symbol="AAPL",
                name="Apple Inc.", summary_stats=sample_summary_stats,
            )
            user_content = (
                mock_anthropic.messages.create.call_args.kwargs["messages"][0]["content"]
            )
            assert keyword.lower() in user_content.lower(), (
                f"Expected keyword '{keyword}' in prompt for chart_type='{chart_type}'"
            )

    def test_result_is_sanitised_before_return(
        self, mock_anthropic, sample_summary_stats
    ):
        """The raw API response is sanitised — em dash should be replaced."""
        mock_anthropic.messages.create.return_value.content[0].text = (
            "Strong growth \u2014 especially in H2."
        )
        result = analyse_chart(
            chart_type="candlestick", symbol="AAPL",
            name="Apple Inc.", summary_stats=sample_summary_stats,
        )
        assert "\u2014" not in result
        assert "-" in result


# ── Cache behaviour ───────────────────────────────────────────────────────────

@pytest.mark.unit
class TestCaching:

    def test_second_call_hits_cache_not_api(
        self, mock_anthropic, sample_summary_stats
    ):
        """The API should only be called once for the same symbol+chart_type."""
        r1 = analyse_chart("candlestick", "CACHE_TEST", "Cache Test", sample_summary_stats)
        r2 = analyse_chart("candlestick", "CACHE_TEST", "Cache Test", sample_summary_stats)
        assert r1 == r2
        assert mock_anthropic.messages.create.call_count == 1

    def test_different_chart_types_cached_separately(
        self, mock_anthropic, sample_summary_stats
    ):
        analyse_chart("candlestick", "AAPL", "Apple", sample_summary_stats)
        analyse_chart("drawdown",    "AAPL", "Apple", sample_summary_stats)
        assert mock_anthropic.messages.create.call_count == 2

    def test_different_symbols_cached_separately(
        self, mock_anthropic, sample_summary_stats
    ):
        analyse_chart("candlestick", "AAPL", "Apple",     sample_summary_stats)
        analyse_chart("candlestick", "MSFT", "Microsoft", sample_summary_stats)
        assert mock_anthropic.messages.create.call_count == 2

    def test_cache_key_format_is_symbol_underscore_chart_type(
        self, mock_anthropic, sample_summary_stats
    ):
        """Cache entries use '{symbol}_{chart_type}' as the key."""
        analyse_chart("price_ma", "SPY", "SPDR S&P 500", sample_summary_stats)
        assert "SPY_price_ma" in _cache


# ── Fallback behaviour ────────────────────────────────────────────────────────

@pytest.mark.unit
class TestFallback:

    def test_fallback_on_api_constructor_exception(
        self, mocker, sample_summary_stats
    ):
        """If Anthropic() raises, a non-empty fallback string is returned."""
        mocker.patch("anthropic.Anthropic", side_effect=Exception("No API key"))
        result = analyse_chart(
            chart_type="candlestick", symbol="FALLBACK",
            name="Fallback Asset", summary_stats=sample_summary_stats,
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_fallback_on_api_create_exception(
        self, mocker, sample_summary_stats
    ):
        """If messages.create() raises, a non-empty fallback string is returned."""
        mock_client = mocker.MagicMock()
        mock_client.messages.create.side_effect = Exception("Rate limit")
        mocker.patch("anthropic.Anthropic", return_value=mock_client)
        result = analyse_chart(
            chart_type="price_ma", symbol="ERR",
            name="Error Asset", summary_stats=sample_summary_stats,
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_fallback_contains_symbol(
        self, mocker, sample_summary_stats
    ):
        mocker.patch("anthropic.Anthropic", side_effect=Exception("API error"))
        result = analyse_chart(
            chart_type="drawdown", symbol="FBSYM",
            name="Fallback Symbol Asset", summary_stats=sample_summary_stats,
        )
        assert "FBSYM" in result

    def test_fallback_for_unknown_chart_type(
        self, mocker, sample_summary_stats
    ):
        """Unknown chart types must not raise KeyError — generic fallback used."""
        mocker.patch("anthropic.Anthropic", side_effect=Exception("API error"))
        result = analyse_chart(
            chart_type="unknown_chart_xyz", symbol="AAPL",
            name="Apple Inc.", summary_stats=sample_summary_stats,
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_fallback_still_cached(
        self, mocker, sample_summary_stats
    ):
        """Fallback results are cached so the API is not retried on the next call."""
        mock_client = mocker.MagicMock()
        mock_client.messages.create.side_effect = Exception("Error")
        mocker.patch("anthropic.Anthropic", return_value=mock_client)
        analyse_chart("candlestick", "CACHED_FB", "Test", sample_summary_stats)
        assert "CACHED_FB_candlestick" in _cache


# ── Sanitiser ─────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestSanitiser:

    def test_em_dash_replaced_with_hyphen(
        self, mock_anthropic, sample_summary_stats
    ):
        mock_anthropic.messages.create.return_value.content[0].text = (
            "Strong performance \u2014 especially in Q4."
        )
        result = analyse_chart(
            "candlestick", "SAN1", "Test", sample_summary_stats,
        )
        assert "\u2014" not in result
        assert "-" in result

    def test_en_dash_replaced_with_hyphen(
        self, mock_anthropic, sample_summary_stats
    ):
        mock_anthropic.messages.create.return_value.content[0].text = (
            "Returns were 10\u201315% over the period."
        )
        result = analyse_chart("price_ma", "SAN2", "Test", sample_summary_stats)
        assert "\u2013" not in result

    def test_smart_quotes_replaced_with_straight_quotes(
        self, mock_anthropic, sample_summary_stats
    ):
        mock_anthropic.messages.create.return_value.content[0].text = (
            "\u201cStrong\u201d and \u2018notable\u2019 performance."
        )
        result = analyse_chart("drawdown", "SAN3", "Test", sample_summary_stats)
        assert "\u201c" not in result
        assert "\u201d" not in result
        assert "\u2018" not in result
        assert "\u2019" not in result

    def test_unicode_ellipsis_replaced_with_three_dots(
        self, mock_anthropic, sample_summary_stats
    ):
        mock_anthropic.messages.create.return_value.content[0].text = (
            "Performance improved\u2026 significantly."
        )
        result = analyse_chart("price_ma", "SAN4", "Test", sample_summary_stats)
        assert "\u2026" not in result
        assert "..." in result

    def test_non_breaking_space_replaced_with_regular_space(
        self, mock_anthropic, sample_summary_stats
    ):
        mock_anthropic.messages.create.return_value.content[0].text = (
            "Return\u00a0was\u00a024.5%."
        )
        result = analyse_chart("cumulative_return", "SAN5", "Test", sample_summary_stats)
        assert "\u00a0" not in result
