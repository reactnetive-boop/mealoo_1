# Mealoo API Reference Docs

Role-based reference for every API in the backend — one file per consumer app.
Each file lists the endpoints grouped by Swagger tag, with purpose, request/response
shapes, the mobile screen that calls them, and a source-file map (endpoint file +
service file) so change requests can be located quickly.

| File | Role | Endpoints |
|---|---|---|
| [provider-apis.md](provider-apis.md) | Provider / vendor / kitchen app | 44 |
| [user-apis.md](user-apis.md) | Customer app | 58 |
| [delivery-boy-apis.md](delivery-boy-apis.md) | Delivery partner app (`Mealoo_D`) — includes a verified screen → API map | 29 |
| [admin-apis.md](admin-apis.md) | Admin panel | 61 |

## Regenerating

These files are generated from the live OpenAPI spec. After adding or changing
endpoints, run (with the backend running on `localhost:8000`):

```
python scripts/gen_api_docs.py
```

Endpoint purpose and screen info come from each route's `summary`/`description`
in the endpoint files — keep those rich when adding new APIs. Role-specific
business policies (e.g. the Package Switch Policy in `user-apis.md`) live as
`extra` sections in `scripts/gen_api_docs.py`, so they survive regeneration.
