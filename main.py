"""MailerLite Connector extension — entry point with module hot-reload."""
from __future__ import annotations

import sys
import os

_dir = os.path.dirname(os.path.abspath(__file__))
if _dir not in sys.path:
    sys.path.insert(0, _dir)

for _m in list(sys.modules):
    if _m in ("app", "accounts", "ml_api", "capability", "params", "response_models",
              "handlers_accounts", "handlers_subscribers", "handlers_groups_segments",
              "handlers_campaigns", "handlers_automations", "handlers_forms_fields",
              "handlers_webhooks_reference", "handlers_capability",
              "skeleton", "panels"):
        del sys.modules[_m]

from app import ext, chat  # noqa: E402, F401

import skeleton                       # noqa: E402, F401
import handlers_accounts              # noqa: E402, F401
import handlers_subscribers           # noqa: E402, F401
import handlers_groups_segments       # noqa: E402, F401
import handlers_campaigns             # noqa: E402, F401
import handlers_automations           # noqa: E402, F401
import handlers_forms_fields          # noqa: E402, F401
import handlers_webhooks_reference    # noqa: E402, F401
import handlers_capability            # noqa: E402, F401
import panels                         # noqa: E402, F401
