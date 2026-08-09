"""App-level login gate for the Streamlit dashboard (streamlit-authenticator).

This is UNRELATED to ANAPLAN_USER / ANAPLAN_PASSWORD (see analyzer.py /
AnaplanConfig), which is the backend credential the app uses to call
Anaplan's REST API. This module controls who is allowed to open the
Streamlit UI at all, before any Anaplan call is ever made.

Required env vars (injected via Secret Manager --set-secrets in Cloud Run,
NEVER committed to the repo or baked into the image):
  APP_LOGIN_USER            - the single shared login username
  APP_LOGIN_PASSWORD_HASH   - bcrypt hash of the login password
                               (generate once locally, see comment below)
  APP_COOKIE_KEY            - random signing key for the auth cookie;
                               must stay stable across restarts/instances
                               or users get logged out unexpectedly

To generate APP_LOGIN_PASSWORD_HASH locally (one-off, NOT part of CI):
    uv run python -c "import streamlit_authenticator as stauth; \
        print(stauth.Hasher.hash('the-plaintext-password'))"
"""
import os

import streamlit as st
import streamlit_authenticator as stauth


def require_login() -> None:
    """Render the login form and halt the script (st.stop()) until the
    user is authenticated. Call this once, near the top of dashboard.py,
    before st.sidebar / fetch_all_model_data are reached."""
    login_user = os.environ.get("APP_LOGIN_USER")
    password_hash = os.environ.get("APP_LOGIN_PASSWORD_HASH")
    cookie_key = os.environ.get("APP_COOKIE_KEY")

    if not login_user or not password_hash or not cookie_key:
        st.error(
            "APP_LOGIN_USER / APP_LOGIN_PASSWORD_HASH / APP_COOKIE_KEY が"
            "環境変数に設定されていません（アプリのログインゲート用。"
            "Anaplan認証情報とは別物です）。"
        )
        st.stop()

    credentials = {
        "usernames": {
            login_user: {
                "email": f"{login_user}@local",
                "first_name": login_user,
                "last_name": "",
                "password": password_hash,  # pre-hashed bcrypt string
                "logged_in": False,
                "failed_login_attempts": 0,
            }
        }
    }

    authenticator = stauth.Authenticate(
        credentials,
        cookie_name="anaplan_model_analyzer_auth",
        cookie_key=cookie_key,
        cookie_expiry_days=7,
        auto_hash=False,  # password field above is already a bcrypt hash
    )

    authenticator.login(location="main")

    auth_status = st.session_state.get("authentication_status")

    if auth_status is False:
        st.error("ユーザー名またはパスワードが正しくありません。")
        st.stop()
    elif auth_status is None:
        st.info("ログインしてください。")
        st.stop()
    # auth_status is True -> fall through, render the rest of the app.

    with st.sidebar:
        st.caption(f"ログイン中: {st.session_state.get('name', login_user)}")
        authenticator.logout("ログアウト", "sidebar")
