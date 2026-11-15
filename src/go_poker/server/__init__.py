"""The FastAPI server that hosts private tables in memory and speaks the `go-poker.v1` wire protocol (ADR 0009).

It is the only layer that knows about transports, identifiers and credentials. It imports `app`, `game` and `core`,
and nothing imports it (`tests/test_layering.py`). Every wire value is produced by an explicit mapping function
(`mapping`) into an explicit wire model (`dto`): no engine or application value is ever copied onto the wire in bulk
(ADR 0008 §2).
"""
