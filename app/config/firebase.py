import json
import logging
from pathlib import Path
from typing import Optional

import firebase_admin
from firebase_admin import auth, credentials, firestore

from app.config.settings import get_settings

logger = logging.getLogger("ghostgrid.firebase")

_firebase_app: Optional[firebase_admin.App] = None


def initialize_firebase() -> Optional[firebase_admin.App]:
    """
    Initializes Firebase Admin SDK using either:
    1. A raw JSON string from FIREBASE_CREDENTIALS_JSON (Render / Cloud environment)
    2. A JSON file path from FIREBASE_CREDENTIALS_PATH (Local dev)
    Falls back gracefully in mock/dev mode if neither is configured.
    """
    global _firebase_app

    if _firebase_app is not None:
        return _firebase_app

    settings = get_settings()
    cred = None

    if settings.FIREBASE_CREDENTIALS_JSON:
        try:
            cert_dict = json.loads(settings.FIREBASE_CREDENTIALS_JSON)
            cred = credentials.Certificate(cert_dict)
            logger.info("Initializing Firebase using FIREBASE_CREDENTIALS_JSON env var")
        except Exception as exc:
            logger.error("Failed to parse FIREBASE_CREDENTIALS_JSON: %s", exc)

    if cred is None and settings.FIREBASE_CREDENTIALS_PATH:
        cred_path = Path(settings.FIREBASE_CREDENTIALS_PATH)
        if cred_path.is_file():
            try:
                cred = credentials.Certificate(str(cred_path))
                logger.info("Initializing Firebase using file at %s", cred_path)
            except Exception as exc:
                logger.error("Failed to load Firebase cert from file %s: %s", cred_path, exc)
        else:
            logger.warning(
                "Firebase cert file '%s' not found. Dev fallback active.",
                settings.FIREBASE_CREDENTIALS_PATH,
            )

    if cred is not None:
        try:
            _firebase_app = firebase_admin.initialize_app(cred)
            logger.info("Firebase Admin SDK initialized successfully")
        except Exception as exc:
            logger.error("Failed to initialize Firebase Admin SDK: %s", exc)
            _firebase_app = None
    else:
        logger.warning(
            "GhostGrid running without active Firebase credentials (Mock Dev Mode)."
        )

    return _firebase_app


def get_auth():
    """Returns the Firebase Auth module handle."""
    return auth


def get_firestore_client():
    """Returns Firestore client instance if Firebase is initialized."""
    if _firebase_app is not None:
        return firestore.client()
    return None