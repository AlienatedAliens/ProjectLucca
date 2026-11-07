from unittest.mock import patch, MagicMock
import httpx

class MockResponse:
    status_code = 200
    text = "<html>test</html>"

print("Before patch:", isinstance(httpx.Client.get, MagicMock))

with patch("httpx.Client.get", return_value=MockResponse()):
    print("Inside patch:", isinstance(httpx.Client.get, MagicMock))
    print("Has mock_calls:", hasattr(httpx.Client.get, "mock_calls"))

print("After patch:", isinstance(httpx.Client.get, MagicMock))
