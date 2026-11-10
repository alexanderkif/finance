"""English service and control text for the chat API.

Conversational text is written by the model. These strings are limited to
service failures and hard safety responses.
"""

UNAVAILABLE = (
    "The assistant service is temporarily unavailable. "
    "Try again in about a minute."
)
TIMEOUT = (
    "The assistant took too long to respond. Try again in about a minute."
)
LOOP = (
    "The assistant could not complete the request. Try again in about a minute."
)
NOT_CONFIGURED = "The assistant is not configured. Try again later."
RATE_LIMITED = (
    "The free Gemini quota has been used up or rate limited. "
    "Wait about a minute, then try again."
)
