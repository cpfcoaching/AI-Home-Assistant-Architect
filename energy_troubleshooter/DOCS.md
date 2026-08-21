# Energy Data Troubleshooter

This App audits Home Assistant Energy preferences, validation results, SmartHub statistics, and energy entity metadata. It is read-only and does not alter Energy configuration.

Version 0.2.0 explains the configured import/export mappings, checks whether their meter families are synchronized, ignores empty Home Assistant validation slots, and presents every real finding as evidence, impact, and a recommended action.

SmartHub statistics are presented as utility-side reconciliation data rather than being treated as mandatory for a responsive local Energy dashboard.
