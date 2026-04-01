# Processing layer — pure tabular shaping, no I/O.
#
# Each module owns one domain's groupby / aggregate / rank / sort logic.
# Services fetch data via repositories, then delegate here.
#
# Polars adoption path:
#   Replace the internals of each processor method.
#   Signatures (list[dict] in → dict/list[dict] out) are the stable contract.
