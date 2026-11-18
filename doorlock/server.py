"""Small web server the owner opens from the SMS link.

It shows the visitor's photo with Unlock / Deny buttons. The server only records
the owner's answer; the camera loop (AccessController) is what moves the servo.
"""
from __future__ import annotations

import time

from flask import Flask, abort, render_template_string, send_file

from .access_requests import RequestStore

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Door access request</title>
<style>
  body { font-family: system-ui, sans-serif; background: #111827; color: #f9fafb;
         margin: 0; padding: 16px; text-align: center; }
  main { max-width: 480px; margin: 0 auto; }
  img { width: 100%; border-radius: 12px; margin: 12px 0; }
  form { display: inline-block; width: 48%; }
  button { width: 100%; padding: 16px; font-size: 18px; font-weight: 600;
           border: 0; border-radius: 10px; color: #fff; cursor: pointer; }
  .unlock { background: #16a34a; } .deny { background: #dc2626; }
  .status { font-size: 20px; padding: 16px; border-radius: 10px; background: #1f2937; }
</style>
</head>
<body><main>
  <h1>Someone is at the door</h1>
  <p>The system could not recognise this person.</p>
  <img src="{{ url_for('photo', token=req.token) }}" alt="Visitor photo">
  {% if req.status == 'pending' %}
    <form method="post" action="{{ url_for('unlock', token=req.token) }}">
      <button class="unlock">Unlock door</button></form>
    <form method="post" action="{{ url_for('deny', token=req.token) }}">
      <button class="deny">Deny</button></form>
  {% elif req.status == 'approved' %}
    <p class="status">Door unlocked.</p>
  {% elif req.status == 'denied' %}
    <p class="status">Access denied.</p>
  {% else %}
    <p class="status">This request has expired.</p>
  {% endif %}
</main></body>
</html>"""


def create_app(store: RequestStore) -> Flask:
    app = Flask(__name__)

    def load(token: str):
        request = store.get(token, time.time())
        if request is None:
            abort(404)
        return request

    @app.get("/r/<token>")
    def view(token: str):
        return render_template_string(PAGE, req=load(token))

    @app.get("/r/<token>/photo")
    def photo(token: str):
        request = load(token)
        if not request.photo_path.exists():
            abort(404)
        return send_file(request.photo_path, mimetype="image/jpeg")

    def decide(token: str, approve: bool):
        request = store.decide(token, approve, time.time())
        if request is None:
            abort(404)
        return render_template_string(PAGE, req=request)

    # State-changing actions are POST only, so link previews can't trigger them.
    @app.post("/r/<token>/unlock")
    def unlock(token: str):
        return decide(token, approve=True)

    @app.post("/r/<token>/deny")
    def deny(token: str):
        return decide(token, approve=False)

    return app
