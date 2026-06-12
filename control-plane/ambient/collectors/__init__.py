"""Ambient context collectors.

Collectors should emit AmbientEvent objects only. They should not execute user
mutations, bypass session scope, or persist secrets.
"""
