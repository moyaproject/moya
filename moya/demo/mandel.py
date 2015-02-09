from moya.run import get_callable_from_document

call = get_callable_from_document('mandel.xml', 'mandel')

from moya.tools import timer
with timer("Calculate mandelbrot set", write_file="mandeltimes.csv"):
    call()
