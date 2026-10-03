"""Automated SOP evidence runner: python -m sop <command>.

Runs the experiments behind the thesis SOPs, stores raw data, and renders one
report. It measures and reports; it never invents a number: a step that needs
hardware that is absent is reported as skipped, and values taken from the
literature are labelled "cited".
"""
