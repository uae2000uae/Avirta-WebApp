"""Flask routes for AI settings, the AI question generator and the AI validator.

Registered from app.py via ``register_ai_routes(app, ...)``. Page endpoints keep
their historic names (``ai_question_generator``, ``save_ai_questions``,
``aivalidator``) so existing links and ``url_for`` calls keep working.
"""
from __future__ import annotations

import io
import json
from datetime import datetime
from functools import wraps

from flask import flash, jsonify, redirect, render_template, request, send_file, session, url_for

from questionmanagement.ai_engine import batches, checks, config, keys, service
from questionmanagement.ai_engine import generator as ai_generator
from questionmanagement.ai_engine import validator as ai_validator
from questionmanagement.ai_engine.client import AIError


def register_ai_routes(app, *, admin_setup, question_bank, category_manager, question_uploader,
                       get_categories):
    def is_admin() -> bool:
        return bool(session.get("admin_authenticated", False))

    def admin_page(fn):
        @wraps(fn)
        def wrapper(*a, **k):
            if not is_admin():
                flash("You must be logged in as an admin to access this page.", "error")
                return redirect(url_for("admin_controls"))
            return fn(*a, **k)
        return wrapper

    def admin_api(fn):
        @wraps(fn)
        def wrapper(*a, **k):
            if not is_admin():
                return jsonify({"ok": False, "error": "Not authenticated"}), 401
            return fn(*a, **k)
        return wrapper

    def bank_questions():
        question_bank.load_questions()
        return [q for q in question_bank.questions.values() if isinstance(q, dict)]

    def push_to_github(message: str) -> str:
        try:
            from contents.admin_controls.github_integration import GitHubIntegration, push_all_amended_questions_async
            if getattr(GitHubIntegration(), "token", None):
                push_all_amended_questions_async(commit_message=message, detach=True)
                admin_setup.record_stat("github_auto_pushes")
                return "Upload to GitHub started in the background."
            return "GitHub upload not started: GITHUB_TOKEN is missing."
        except Exception as exc:  # never block the save on GitHub
            return f"GitHub sync skipped ({type(exc).__name__})."

    def key_statuses(cfg):
        out = {oid: keys.key_status(oid) for oid in config.OPTION_IDS}
        custom = out["custom"]
        if not custom["configured"] and service._is_local(cfg["options"]["custom"].get("base_url", "")):
            custom.update({"configured": True, "source": "not needed for a local service", "hint": "", "local": True})
        return out

    def ai_state():
        cfg = admin_setup.get_ai_config()
        active_rt = config.resolve_runtime(cfg)
        return {
            "config": cfg,
            "catalog": config.frontend_catalog(),
            "keys": key_statuses(cfg),
            "presets": admin_setup.get_saved_api_settings(),
            "on_cloud_run": keys.on_cloud_run(),
            "active_summary": {"option": active_rt["option_id"], "label": active_rt["label"],
                               "model": active_rt["model"], "quality": active_rt["quality"]},
        }

    def body() -> dict:
        return request.get_json(silent=True) or {}

    # ------------------------------------------------------------ settings API
    @app.route("/admin/ai/state", methods=["GET"], endpoint="ai_settings_state")
    @admin_api
    def ai_settings_state():
        return jsonify({"ok": True, **ai_state()})

    @app.route("/admin/ai/config", methods=["POST"], endpoint="ai_settings_save")
    @admin_api
    def ai_settings_save():
        incoming = body().get("config")
        if not isinstance(incoming, dict):
            return jsonify({"ok": False, "error": "Missing configuration"}), 400
        admin_setup.set_ai_config(incoming)
        return jsonify({"ok": True, "message": "AI settings saved.", **ai_state()})

    @app.route("/admin/ai/key", methods=["POST"], endpoint="ai_settings_key")
    @admin_api
    def ai_settings_key():
        data = body()
        option = data.get("option")
        if option not in config.OPTION_IDS:
            return jsonify({"ok": False, "error": "Unknown AI option"}), 400
        ok, message = keys.save_key(option, data.get("key") or "")
        admin_setup.log_event(f"API key for {option} {'saved' if ok else 'not saved'}: {message}",
                              level="SUCCESS" if ok else "WARNING", category="AI")
        return jsonify({"ok": ok, "message": message, "status": key_statuses(admin_setup.get_ai_config())[option]}), (200 if ok else 400)

    def _client_for_request():
        data = body()
        option = data.get("option") if data.get("option") in config.OPTION_IDS else None
        overrides = data.get("overrides") if isinstance(data.get("overrides"), dict) else None
        return service.build_client(admin_setup, option, overrides)

    @app.route("/admin/ai/test", methods=["POST"], endpoint="ai_settings_test")
    @admin_api
    def ai_settings_test():
        try:
            client, runtime = _client_for_request()
            result = client.test()
        except AIError as exc:
            return jsonify({"ok": False, "error": str(exc)})
        msg = f"Connected to {runtime['label']} · {result['model']} · {result['latency_ms']} ms"
        if not result.get("sample_correct"):
            msg += " (answered, but the sample answer looked wrong)"
        return jsonify({"ok": True, "message": msg, **result})

    @app.route("/admin/ai/models", methods=["POST"], endpoint="ai_settings_models")
    @admin_api
    def ai_settings_models():
        try:
            client, _ = _client_for_request()
            return jsonify({"ok": True, "models": client.list_models()})
        except AIError as exc:
            return jsonify({"ok": False, "error": str(exc)})

    @app.route("/admin/ai/presets", methods=["POST"], endpoint="ai_settings_presets")
    @admin_api
    def ai_settings_presets():
        data = body()
        action, name = data.get("action"), (data.get("name") or "").strip()
        if action == "save":
            ok, message = admin_setup.save_api_settings(name, data.get("preset") or {})
        elif action == "delete":
            ok, message = admin_setup.delete_api_settings(name)
        elif action == "apply":
            preset = admin_setup.get_saved_api_settings().get(name)
            if not preset:
                return jsonify({"ok": False, "error": "Preset not found"}), 404
            cfg = admin_setup.get_ai_config()
            option = preset.get("option", "openai")
            cfg["options"][option] = config.normalize_option_config(option, preset)
            cfg["active"] = option
            admin_setup.set_ai_config(cfg)
            ok, message = True, f"Preset '{name}' applied and {config.OPTIONS[option]['label']} is now active."
        else:
            return jsonify({"ok": False, "error": "Unknown action"}), 400
        return jsonify({"ok": ok, "message": message, **ai_state()}), (200 if ok else 400)

    # --------------------------------------------------------------- generator
    @app.route("/ai_question_generator", methods=["GET"], endpoint="ai_question_generator")
    @admin_page
    def ai_question_generator():
        batch_id = request.args.get("batch_id")
        questions = batches.get_batch(batch_id) if batch_id else None
        metadata = batches.get_batch_metadata(batch_id) if batch_id else None
        return render_template(
            "ai_question_generator.html",
            categories=get_categories(),
            generated_questions=questions,
            metadata=metadata,
            batch_id=batch_id if questions else None,
            ai=ai_state(),
            admin_setup=admin_setup,
        )

    @app.route("/api/ai/generate", methods=["POST"], endpoint="ai_generate_start")
    @admin_api
    def ai_generate_start():
        data = body()
        topic = (data.get("topic") or "").strip()
        if not topic:
            return jsonify({"ok": False, "error": "Please enter a topic."}), 400
        running = service.jobs.latest("generate")
        if running and running["status"] == "running":
            return jsonify({"ok": False, "error": "A generation is already running.", "job_id": running["id"]}), 409
        try:
            client, runtime = service.build_client(admin_setup)
        except AIError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        req = {
            "topic": topic[:200],
            "focus": (data.get("focus") or "").strip()[:500],
            "count": data.get("count", 10),
            "types": data.get("types") or list(checks.TYPES),
            "difficulty": data.get("difficulty") or "mixed",
            "language": data.get("language") or "arabic",
            "explanations": bool(data.get("explanations", True)),
            "verify": bool(data.get("verify", True)),
            "use_sources": bool(data.get("use_sources", runtime.get("use_sources", True))),
            "category": (data.get("category") or "").strip(),
        }
        job_id = service.jobs.create("generate", target=int(req["count"] or 10), generated=0,
                                     model=runtime["model"], option=runtime["label"])
        service.run_in_background(job_id, ai_generator.generate, client, runtime, req, bank_questions())
        admin_setup.log_event(f"AI generation started: '{req['topic']}' ({req['count']} questions, {runtime['model']})",
                              category="AI")
        return jsonify({"ok": True, "job_id": job_id})

    @app.route("/api/ai/jobs/<job_id>", methods=["GET"], endpoint="ai_job_status")
    @admin_api
    def ai_job_status(job_id):
        job = service.jobs.get(job_id)
        if not job:
            return jsonify({"ok": False, "error": "Job not found (the service may have restarted)."}), 404
        return jsonify({"ok": True, "job": job})

    @app.route("/save_ai_questions", methods=["POST"], endpoint="save_ai_questions")
    @admin_page
    def save_ai_questions():
        batch_id = request.form.get("batch_id")
        questions = batches.get_batch(batch_id) if batch_id else None
        if not questions:
            flash("This batch could not be found.", "error")
            return redirect(url_for("ai_question_generator"))

        existing = (request.form.get("existing_category") or "").strip()
        new_name = (request.form.get("new_category") or "").strip()
        if existing and existing != "__new__":
            category_id = existing
        elif new_name:
            category_id = "_".join(new_name.lower().split())
            if not category_manager.get_category(category_id):
                category_manager.add_category(category_id, new_name)
        else:
            flash("Choose a category or enter a new category name.", "error")
            return redirect(url_for("ai_question_generator", batch_id=batch_id))

        index = ai_generator.build_bank_index(bank_questions(), include_recent_batches=False)
        saved, skipped = 0, []
        for i, original in enumerate(questions):
            if f"include_{i}" not in request.form:
                continue
            q = checks.clean_question({
                **original,
                "question": request.form.get(f"question_{i}", original.get("question")),
                "correct_answer": request.form.get(f"answer_{i}", original.get("correct_answer")),
                "explanation": request.form.get(f"explanation_{i}", original.get("explanation", "")),
                "points": request.form.get(f"points_{i}", original.get("points")),
                "options": [request.form.get(f"option_{i}_{j}", o) for j, o in enumerate(original.get("options") or [])],
            }, keep_ai_fields=False)
            problems = checks.check_question(q)
            if problems:
                skipped.append(f"#{i + 1}: {problems[0]}")
                continue
            dup = index.find_duplicate(q)
            if dup:
                skipped.append(f"#{i + 1}: already in the bank ({dup[0].get('category_id')})")
                continue
            data = checks.to_bank_shape(q)
            ok, _ = question_bank.add_question(data, category_id, data["points"])
            if ok:
                question_uploader.add_question(dict(data), category_id)
                index.add(q)
                saved += 1
        question_uploader.remove_duplicate_questions()
        question_bank.load_questions()

        if saved:
            admin_setup.record_stat("questions_saved", saved)
            admin_setup.record_stat("ai_generations")
            admin_setup.log_event(f"Saved {saved} AI-generated question(s) to '{category_id}'",
                                  level="SUCCESS", category="AI")
            flash(f"Added {saved} question(s) to '{category_id}'. " + push_to_github("Add AI-generated questions"))
        else:
            flash("No questions were added.", "warning")
        if skipped:
            flash("Skipped: " + "; ".join(skipped[:8]), "warning")
        return redirect(url_for("ai_question_generator") if saved else url_for("ai_question_generator", batch_id=batch_id))

    # --------------------------------------------------------------- validator
    @app.route("/aivalidator", methods=["GET"], endpoint="aivalidator")
    @admin_page
    def aivalidator():
        return render_template("aivalidator.html", categories=get_categories(), ai=ai_state(),
                               admin_setup=admin_setup)

    @app.route("/api/ai/validate", methods=["POST"], endpoint="ai_validate_start")
    @admin_api
    def ai_validate_start():
        running = service.jobs.latest("validate")
        if running and running["status"] == "running":
            return jsonify({"ok": False, "error": "A review is already running.", "job_id": running["id"]}), 409
        if request.files:
            options = json.loads(request.form.get("options") or "{}")
            groups = {}
            for f in request.files.getlist("files"):
                try:
                    items = json.loads(f.read().decode("utf-8"))
                except Exception:
                    return jsonify({"ok": False, "error": f"{f.filename} is not valid JSON."}), 400
                if not isinstance(items, list):
                    return jsonify({"ok": False, "error": f"{f.filename} must contain a list of questions."}), 400
                name = (f.filename or "upload").rsplit(".", 1)[0]
                groups[name] = [dict(q, id=str(q.get("id") or f"{name}-{i + 1}")) for i, q in enumerate(items)
                                if isinstance(q, dict)]
            source = "upload"
        else:
            data = body()
            options = data.get("options") or {}
            wanted = [c for c in (data.get("categories") or []) if isinstance(c, str)]
            all_q = bank_questions()
            groups = {c: [q for q in all_q if q.get("category_id") == c] for c in wanted}
            groups = {c: qs for c, qs in groups.items() if qs}
            source = "bank"
        count = sum(len(v) for v in groups.values())
        if not count:
            return jsonify({"ok": False, "error": "Choose at least one category (or upload a file) with questions."}), 400
        if count > 600:
            return jsonify({"ok": False, "error": f"{count} questions selected; review at most 600 at a time."}), 400
        try:
            client, runtime = service.build_client(admin_setup)
        except AIError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        job_id = service.jobs.create("validate", total=count, model=runtime["model"], option=runtime["label"])
        service.run_in_background(job_id, ai_validator.review, client, runtime, groups=groups,
                                  bank_questions=bank_questions(), options=options, source=source)
        admin_setup.log_event(f"AI review started for {count} question(s) ({runtime['model']})", category="AI")
        return jsonify({"ok": True, "job_id": job_id, "total": count})

    @app.route("/api/ai/validate/<job_id>/results", methods=["GET"], endpoint="ai_validate_results")
    @admin_api
    def ai_validate_results(job_id):
        data = ai_validator.load_results(job_id)
        if not data:
            return jsonify({"ok": False, "error": "Results not found."}), 404
        return jsonify({"ok": True, **data})

    @app.route("/api/ai/validate/<job_id>/apply", methods=["POST"], endpoint="ai_validate_apply")
    @admin_api
    def ai_validate_apply(job_id):
        decisions = [d for d in (body().get("decisions") or []) if isinstance(d, dict)]
        if not decisions:
            return jsonify({"ok": False, "error": "Nothing selected."}), 400
        try:
            counts = ai_validator.apply_changes(job_id, decisions, question_bank)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        if counts["updated"] or counts["deleted"]:
            admin_setup.record_stat("questions_validated", counts["updated"] + counts["deleted"])
            admin_setup.log_event(f"AI review applied: {counts['updated']} updated, {counts['deleted']} deleted",
                                  level="SUCCESS", category="AI")
            counts["github"] = push_to_github("Apply AI review corrections")
        return jsonify({"ok": True, **counts})

    @app.route("/api/ai/validate/<job_id>/download", methods=["POST"], endpoint="ai_validate_download")
    @admin_api
    def ai_validate_download(job_id):
        decisions = [d for d in (body().get("decisions") or []) if isinstance(d, dict)]
        try:
            items = ai_validator.corrected_file(job_id, decisions)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 404
        buf = io.BytesIO(json.dumps(items, ensure_ascii=False, indent=2).encode("utf-8"))
        name = f"reviewed_questions_{datetime.now():%Y%m%d_%H%M}.json"
        return send_file(buf, mimetype="application/json", as_attachment=True, download_name=name)
