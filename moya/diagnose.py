"""Diagnose common problems"""

from __future__ import unicode_literals

_moya_exception_errors = {

    "db.operational-error": """This error can occur when the database doesn't match Moya's model definitions.\n\n"""
                            """Do you need to run *moya db sync*?""",

    "db.error": """This error typically occurs when the database doesn't match Moya's model definitions.\n\n"""
                """Do you need to run *moya db sync*?""",

    "widget.app-required": """An application is required to display a widget.\n\n"""
                           """You may need to add a &lt;install/&gt; tag to your *server.xml*.""",

    "widget.ambiguous-app": """Moya doesn't know which application to use for this widget because the library is installed multiple times.\n\n"""
                            """You can resolve this ambiguity by adding a 'from' attribute to the tag."""

}


def diagnose_moya_exception(moya_exc):
    diagnosis = getattr(moya_exc, '_diagnosis', None) or _moya_exception_errors.get(moya_exc.type, None)
    return diagnosis
