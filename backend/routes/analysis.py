"""Stock analysis endpoints — /api/analyze-*"""

import json
import logging
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import Blueprint, request, jsonify, Response, stream_with_context, g

from broker import get_broker
from middleware.auth import require_auth, require_broker
from services.analysis_storage import save_analysis_result
from services.validation import validate_request, AnalyzeStockBody

logger = logging.getLogger(__name__)

analysis_bp = Blueprint("analysis", __name__, url_prefix="/api")


@analysis_bp.route("/analyze-stock", methods=["POST"])
@require_auth
@require_broker
@validate_request(AnalyzeStockBody)
def analyze_stock(body: AnalyzeStockBody):
    """Analyze a single stock on-demand using 3 agents independently."""
    try:
        from agents.workers.stats_agent import stats_agent_node
        from agents.workers.company_health_agent import company_health_agent_node
        from agents.workers.breaking_news_agent import breaking_news_agent_node

        access_token = g.broker_token
        user_id = g.current_user["id"]
        symbol = body.symbol
        instrument_token = body.instrument_token
        llm_provider = body.llm_provider

        logger.info(f"Starting analysis for {symbol} (provider={llm_provider or 'gemini'})")

        state = {
            "symbol": symbol,
            "access_token": access_token,
            "instrument_token": instrument_token,
            "llm_provider": llm_provider,
            "stats_result": None,
            "company_health_result": None,
            "breaking_news_result": None,
            "overall_score": None,
            "verdict": None,
            "risk_factors": None,
            "conflict_summary": None,
            "analyzed_at": None,
        }

        agent_errors = []
        agents_config = [
            ("stats_agent", stats_agent_node, "stats_result"),
            ("company_health_agent", company_health_agent_node, "company_health_result"),
            ("breaking_news_agent", breaking_news_agent_node, "breaking_news_result"),
        ]

        for name, node_fn, result_key in agents_config:
            logger.info(f"Running {name} for {symbol}")
            try:
                result = node_fn(state)
                state[result_key] = result.get(result_key)
                score = state[result_key].get("score", "?") if state[result_key] else "?"
                logger.info(f"{name} completed — score: {score}")
            except Exception as agent_err:
                logger.warning(f"{name} FAILED: {agent_err}")
                agent_errors.append(name)
                state[result_key] = {"score": 3.0, "explanation": f"{name} failed: {str(agent_err)}"}

        logger.info(f"Running synthesizer for {symbol}")
        try:
            from agents.analysis_graph import _synthesizer_node
            synth = _synthesizer_node(state)
            state.update(synth)
            logger.info(f"Synthesizer completed — overall: {state.get('overall_score')}")
        except Exception as synth_err:
            logger.warning(f"Synthesizer FAILED: {synth_err}")
            scores = []
            for key in ["stats_result", "company_health_result", "breaking_news_result"]:
                r = state.get(key)
                if r and isinstance(r, dict):
                    scores.append(r.get("score", 3.0))
            overall = round(sum(scores) / len(scores), 1) if scores else 3.0
            state["overall_score"] = overall
            state["verdict"] = f"Hold — AI verdict unavailable. Score is average of {len(scores)} agent(s)."
            state["analyzed_at"] = datetime.now().isoformat()

        response_data = {
            "success": True,
            "symbol": symbol,
            "overall_score": state.get("overall_score"),
            "verdict": state.get("verdict"),
            "risk_factors": state.get("risk_factors"),
            "conflict_summary": state.get("conflict_summary"),
            "agents": {
                "stats_agent": state.get("stats_result"),
                "company_health_agent": state.get("company_health_result"),
                "breaking_news_agent": state.get("breaking_news_result"),
            },
            "analyzed_at": state.get("analyzed_at"),
        }

        if agent_errors:
            response_data["agent_errors"] = agent_errors

        save_analysis_result(user_id, symbol, response_data)
        logger.info(f"Done — {symbol} overall_score={state.get('overall_score')}, errors={agent_errors}")

        return jsonify(response_data)

    except Exception as e:
        logger.error(f"FATAL analysis error: {e}", exc_info=True)
        return jsonify({"success": False, "error": "Analysis failed"}), 500


@analysis_bp.route("/analyze-stock-stream", methods=["POST"])
@require_auth
@require_broker
@validate_request(AnalyzeStockBody)
def analyze_stock_stream(body: AnalyzeStockBody):
    """SSE endpoint — streams per-agent progress for a single stock analysis."""
    try:
        from agents.analysis_stream import run_analysis_stream

        access_token = g.broker_token
        user_id = g.current_user["id"]
        symbol = body.symbol
        instrument_token = body.instrument_token
        llm_provider = body.llm_provider

        def generate():
            final_data = None
            for event in run_analysis_stream(symbol, access_token, instrument_token, llm_provider=llm_provider):
                yield event
                if event.startswith("event: complete\n"):
                    try:
                        json_str = event.split("data: ", 1)[1].strip()
                        final_data = json.loads(json_str)
                    except Exception:
                        pass

            yield "event: end\ndata: {}\n\n"

            if final_data:
                save_analysis_result(user_id, symbol, final_data)

        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    except Exception as e:
        return jsonify({"success": False, "error": "Stream failed"}), 500


@analysis_bp.route("/analyze-all", methods=["POST"])
@require_auth
@require_broker
def analyze_all_stocks():
    """Analyze all stocks in portfolio."""
    try:
        from agents.analysis_graph import analysis_graph

        access_token = g.broker_token
        user_id = g.current_user["id"]
        broker = get_broker(access_token)
        holdings = broker.get_holdings()

        if not holdings:
            return jsonify({"success": True, "results": [], "message": "No holdings found"})

        results = []
        failed_stocks = []

        data = request.json or {}
        llm_provider = data.get("llm_provider", None)

        def run_analysis(symbol, instrument_token):
            return analysis_graph.invoke({
                "symbol": symbol,
                "access_token": access_token,
                "instrument_token": instrument_token,
                "llm_provider": llm_provider,
                "stats_result": None,
                "company_health_result": None,
                "breaking_news_result": None,
                "overall_score": None,
                "verdict": None,
                "risk_factors": None,
                "conflict_summary": None,
                "analyzed_at": None,
            })

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {}
            for holding in holdings:
                symbol = holding.get("tradingsymbol", "")
                instrument_token = holding.get("instrument_token")
                future = executor.submit(run_analysis, symbol, instrument_token)
                futures[future] = symbol
                time.sleep(0.5)

            for future in as_completed(futures, timeout=300):
                symbol = futures[future]
                try:
                    result = future.result()
                    response_data = {
                        "symbol": symbol,
                        "overall_score": result.get("overall_score"),
                        "verdict": result.get("verdict"),
                        "risk_factors": result.get("risk_factors"),
                        "conflict_summary": result.get("conflict_summary"),
                        "agents": {
                            "stats_agent": result.get("stats_result"),
                            "company_health_agent": result.get("company_health_result"),
                            "breaking_news_agent": result.get("breaking_news_result"),
                        },
                        "analyzed_at": result.get("analyzed_at"),
                    }
                    save_analysis_result(user_id, symbol, response_data)
                    results.append({"symbol": symbol, "success": True, "analysis": response_data})
                except Exception as e:
                    logger.error(f"Error analyzing {symbol}: {e}")
                    failed_stocks.append({"symbol": symbol, "error": str(e)})
                    results.append({"symbol": symbol, "success": False, "error": str(e)})

        return jsonify({
            "success": True,
            "results": results,
            "total_stocks": len(holdings),
            "successful_analyses": len([r for r in results if r.get("success")]),
            "failed_analyses": len(failed_stocks),
            "failed_stocks": failed_stocks,
            "completed_at": datetime.now().isoformat(),
        })

    except Exception as e:
        return jsonify({"success": False, "error": "Analysis failed"}), 500
