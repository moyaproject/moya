# Run mandel.xml without timer

from moya.run import get_callable_from_document

call = get_callable_from_document('mandel.xml', 'mandel')
call()
