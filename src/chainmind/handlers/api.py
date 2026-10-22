"""API Gateway Lambda adapter."""

from mangum import Mangum

from chainmind.api.main import app

handler = Mangum(app)
