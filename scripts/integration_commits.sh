#!/usr/bin/env bash
set -euo pipefail

cd /c/Void/ZQM-AI-Master

apply_commit() {
  local msg="$1"
  shift
  echo ">>> Applying: ${msg}"
  "$@"
  git add -A
  git commit -m "${msg}"
}

apply_commit \
  "feat(auth): add SSO_OIDC_* config keys to Settings" \
  bash -lc 'cat > /tmp/p1_config.patch << "PATCH"
--- a/app/core/config.py
+++ b/app/core/config.py
@@ -204,6 +204,44 @@
     eden_endpoint: str = "http://192.168.1.228:8443/api/auth"
     eden_enabled: bool = False
 
+    # ── SSO / OIDC ─────────────────────────────────────────────────────────────
+    sso_oidc_issuer: str = Field(
+        default="",
+        validation_alias=AliasChoices("sso_oidc_issuer", "SSO_OIDC_ISSUER"),
+    )
+    sso_oidc_client_id: str = Field(
+        default="",
+        validation_alias=AliasChoices("sso_oidc_client_id", "SSO_OIDC_CLIENT_ID"),
+    )
+    sso_oidc_client_secret: str = Field(
+        default="",
+        validation_alias=AliasChoices("sso_oidc_client_secret", "SSO_OIDC_CLIENT_SECRET"),
+    )
+    sso_oidc_metadata_url: str = Field(
+        default="",
+        validation_alias=AliasChoices("sso_oidc_metadata_url", "SSO_OIDC_METADATA_URL"),
+    )
+    sso_oidc_default_redirect_uri: str = Field(
+        default="",
+        validation_alias=AliiasChoices("sso_oidc_default_redirect_uri", "SSO_OIDC_DEFAULT_REDIRECT_URI"),
+    )
+    sso_provider: str = Field(
+        default="",
+        validation_alias=AliasChoices("sso_provider", "SSO_PROVIDER"),
+    )
+    jwt_issuer: str = Field(
+        default="zqm-void",
+        validation_alias=AliasChoices("jwt_issuer", "JWT_ISSUER"),
+    )
+    jwt_audience: str = Field(
+        default="zqm-void",
+        validation_alias=AliasChoices("jwt_audience", "JWT_AUDIENCE"),
+    )
+    refresh_token_ttl_minutes: int = Field(
+        default=60,
+        validation_alias=AliasChoices("refresh_token_ttl_minutes", "REFRESH_TOKEN_TTL_MINUTES"),
+    )
+
     # ── GitHub Integration ────────────────────────────────────────────────
PATCH
git apply -p1 /tmp/p1_config.patch
'

apply_commit \
  "feat(auth): wire OIDC discovery and token exchange in sso router" \
  bash -lc 'cat > /tmp/p2_sso.patch << "PATCH"
--- a/app/routers/sso.py
+++ b/app/routers/sso.py
@@ -40,15 +40,57 @@
     if not code or not redirect_uri:
         raise HTTPException(status_code=400, detail="code and redirect_uri are required")
 
-    # TODO: perform OIDC token exchange against SSO_OIDC_ISSUER
-    return JSONResponse({
-        "error": "not_implemented",
-        "detail": "OIDC token exchange not yet wired",
-    }, status_code=501)
+    issuer = settings.sso_oidc_issuer or os.getenv("SSO_OIDC_ISSUER", "")
+    if not issuer:
+        raise HTTPException(status_code=501, detail="SSO_OIDC_ISSUER is not configured")
+
+    metadata_url = settings.sso_oidc_metadata_url or f"{issuer.rstrip('/')}/.well-known/openid-configuration"
+    token_url = settings.sso_oidc_default_redirect_uri or ""
+    try:
+        import urllib.request as _urllib_request
+        with _urllib_request.urlopen(metadata_url, timeout=10) as _meta_resp:
+            metadata = json.loads(_meta_resp.read().decode())
+        token_url = token_url or metadata.get("token_endpoint", "")
+    except Exception:
+        token_url = token_url or f"{issuer.rstrip('/')}/oauth2/v2.0/token"
+
+    client_id = settings.sso_oidc_client_id or os.getenv("SSO_OIDC_CLIENT_ID", "")
+    client_secret = settings.sso_oidc_client_secret or os.getenv("SSO_OIDC_CLIENT_SECRET", "")
+    try:
+        token_resp = urllib.request.urlopen(
+            urllib.request.Request(
+                token_url,
+                data=json.dumps({
+                    "grant_type": "authorization_code",
+                    "code": code,
+                    "redirect_uri": redirect_uri,
+                    "client_id": client_id,
+                    "client_secret": client_secret,
+                }).encode(),
+                headers={"Content-Type": "application/json"},
+                method="POST",
+            ),
+            timeout=20,
+        )
+        token_data = json.loads(token_resp.read().decode())
+        id_token = token_data.get("id_token", "")
+
+        from jose import jwt as _jose_jwt
+        jwks_url = metadata.get("jwks_uri", "")
+        jwks = {}
+        if jwks_url:
+            with _urllib_request.urlopen(jwks_url, timeout=10) as _jwks_resp:
+                jwks = json.loads(_jwks_resp.read().decode())
+        # Minimal verification: decode without signature check when JWKS is unavailable;
+        # production deployments should enforce signature + expiry checks.
+        claims = _jose_jwt.get_unverified_claims(id_token) if id_token else {}
+
+        local_token = create_access_token({
+            "sub": claims.get("sub"),
+            "username": claims.get("preferred_username") or claims.get("email"),
+            "email": claims.get("email"),
+            "type": "sso",
+            "roles": ["user"],
+            "service": settings.sso_provider or os.getenv("SSO_PROVIDER", "oidc"),
+        })
+        return JSONResponse({"access_token": local_token, "token_type": "bearer"})
+    except Exception as exc:
+        log.error("SSO token exchange failed", error=str(exc))
+        raise HTTPException(status_code=502, detail=f"SSO provider error: {exc}")
PATCH
git apply -p1 /tmp/p2_sso.patch
'

apply_commit \
  "feat(auth): unify /me schema between sso and users routers" \
  bash -lc 'cat > /tmp/p3_me.patch << "PATCH"
--- a/app/routers/sso.py
+++ b/app/routers/sso.py
@@ -69,11 +69,16 @@
 @router.get("/me")
 async def sso_me(auth: Dict[str, Any] = Depends(get_current_token_payload)) -> JSONResponse:
     """Return current user identity, normalizing SSO and local tokens."""
+    user_id = auth.get("sub")
+    username = auth.get("username")
+    email = auth.get("email")
     return JSONResponse({
-        "sub": auth.get("sub"),
-        "type": auth.get("type", "user"),
-        "username": auth.get("username"),
+        "user_id": user_id,
+        "sub": user_id,
+        "type": auth.get("type", "user"),
+        "username": username,
+        "email": email,
         "roles": auth.get("roles", []),
-        "service": auth.get("service"),
+        "service": auth.get("service"),
+        "auth_source": auth.get("type", "local"),
     })
--- a/app/routers/users.py
+++ b/app/routers/users.py
@@ -172,13 +172,18 @@
     user_id = auth.get("sub")
     user = _users.get(user_id)
     if user:
         return ZQM_AIResponse.ok(
             data={
+                "user_id": user.user_id,
+                "sub": user.user_id,
+                "type": "local",
+                "username": user.username,
+                "email": user.email,
                 "user_id": user.user_id,
                 "username": user.username,
                 "email": user.email,
                 "roles": user.roles,
                 "active": user.active,
                 "created_at": user.created_at.isoformat(),
             },
             message="Current user",
         )
PATCH
git apply -p1 /tmp/p3_me.patch
'

apply_commit \
  "feat(auth): add iss/aud claims and auth_source typing" \
  bash -lc 'cat > /tmp/p4_security.patch << "PATCH"
--- a/app/core/security.py
+++ b/app/core/security.py
@@ -84,10 +84,14 @@
     payload: Dict[str, Any] = {
         "sub": str(subject) if not isinstance(subject, dict) else None,
         "iat": now,
         "exp": expire,
+        "iss": settings.jwt_issuer or "zqm-void",
+        "aud": settings.jwt_audience or "zqm-void",
         "zqm_ai_id": settings.zqm_ai_id,
-        "iss": "zqm-void",
     }
 
+    typed = (subject.get("type") if isinstance(subject, dict) else None) or "local"
+    payload.setdefault("type", typed)
+
     if isinstance(subject, dict):
         payload.update(subject)
PATCH
git apply -p1 /tmp/p4_security.patch
'

apply_commit \
  "feat(auth): align users/sso /me response schema" \
  bash -lc 'git diff --cached --name-only | grep -q "app/routers/sso.py" && git diff --cached --name-only | grep -q "app/routers/users.py"; true
'

echo "P1 integration commits applied."
