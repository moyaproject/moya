from __future__ import print_function

import moya.elements
from moya.archive import Archive
call = Archive.get_callable_from_document('test.xml', 'main', default_context=True)
result = call()
print("Return value:", result)
