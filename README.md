# home-api

iot stuff for my house

hosting this publicly is definitely a good idea! making the code public is an even better idea!

## dev quickstart

- install uv if you don't have it already `curl -LsSf https://astral.sh/uv/install.sh | sh`
- clone repo, cd into it
- `uv sync`
- `uv run python -m app`

## Optional API auth

By default, the API does not require auth.

To require auth for specific routers, set:

- `AUTH_REQUIRED`: comma-separated router prefixes to protect (e.g. `lights,garage`). Leave it empty/unset for no auth.
- `AUTH_API_KEY`: API key that clients must provide in the `X-API-Key` header when auth is enabled.

Notes:

- `/health` is always public.
- If `AUTH_REQUIRED` is non-empty and `AUTH_API_KEY` is missing, the app will fail to start.
- If `AUTH_REQUIRED` contains unknown router prefixes, the app will fail to start.

Example:

```bash
export AUTH_REQUIRED="lights"
export AUTH_API_KEY="secret"
uv run python -m app
```

Unauthenticated request should be rejected:

```bash
curl -i -X POST http://localhost:8000/lights/on
```

Authenticated request succeeds:

```bash
curl -i -X POST http://localhost:8000/lights/on -H "X-API-Key: secret"
```

## TODO

- consider: switch lights config from IPs to mac addresses (+ 10.10.111.123), and it does discovery on startup