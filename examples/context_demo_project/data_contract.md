# Event Metrics Data Contract

Each event row is a dictionary with optional fields:

- `event`: human-readable event name.
- `status`: either `ok` or `failed`; missing status is treated as `ok`.

Malformed rows without a non-empty `event` value should be ignored. Event names
are normalized before counting so that equivalent spellings are grouped
together.
