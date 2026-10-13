"""F2 (ฝ่าย 2) data pipeline: clean → resolve → measure → publish.

Clean: one cleaner per source turns that source's raw snapshot into shared entity tables
(see schema.sql). Every row keeps (source, record_id) so later decisions survive refreshes.
"""
