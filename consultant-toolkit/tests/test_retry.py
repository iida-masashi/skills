"""
Unit tests for retry mechanism

Tests retry decorator and safe execution wrapper.
"""

import time
from unittest.mock import Mock, patch

import pytest
from consultant_toolkit.retry import APIError, NetworkError, retry_on_error, safe_execute


class TestRetryDecorator:
    """Test suite for retry_on_error decorator"""

    def test_successful_execution_no_retry(self):
        """Should execute successfully without retries"""
        mock_func = Mock(return_value="success")
        decorated = retry_on_error(max_retries=3)(mock_func)

        result = decorated()

        assert result == "success"
        assert mock_func.call_count == 1

    def test_retry_on_specified_exception(self):
        """Should retry when specified exception is raised"""
        mock_func = Mock(
            side_effect=[
                ConnectionError("Network error"),
                ConnectionError("Network error"),
                "success",  # Third attempt succeeds
            ]
        )

        decorated = retry_on_error(
            max_retries=3,
            delay=0.01,  # Short delay for testing
            exceptions=(ConnectionError,),
        )(mock_func)

        result = decorated()

        assert result == "success"
        assert mock_func.call_count == 3

    def test_max_retries_exceeded(self):
        """Should raise exception after max retries exceeded"""
        mock_func = Mock(side_effect=ConnectionError("Persistent error"))

        decorated = retry_on_error(
            max_retries=2, delay=0.01, exceptions=(ConnectionError,)
        )(mock_func)

        with pytest.raises(ConnectionError, match="Persistent error"):
            decorated()

        # Should be called 2 times total (initial + 1 retry)
        assert mock_func.call_count == 2

    def test_non_retryable_exception_raised_immediately(self):
        """Should raise non-retryable exceptions immediately"""
        mock_func = Mock(side_effect=ValueError("Invalid input"))

        decorated = retry_on_error(
            max_retries=3,
            delay=0.01,
            exceptions=(ConnectionError, TimeoutError),  # ValueError not in list
        )(mock_func)

        with pytest.raises(ValueError, match="Invalid input"):
            decorated()

        # Should only be called once (no retries)
        assert mock_func.call_count == 1

    def test_exponential_backoff(self):
        """Should use exponential backoff between retries"""
        call_times = []

        def mock_func():
            call_times.append(time.time())
            if len(call_times) < 3:
                raise ConnectionError("Retry")
            return "success"

        decorated = retry_on_error(
            max_retries=3, delay=0.1, backoff=2.0, exceptions=(ConnectionError,)
        )(mock_func)

        result = decorated()

        assert result == "success"
        assert len(call_times) == 3

        # Check delays are increasing (exponential backoff)
        delay1 = call_times[1] - call_times[0]
        delay2 = call_times[2] - call_times[1]

        # delay2 should be approximately 2x delay1 (allowing some timing variance)
        assert delay2 > delay1 * 1.5

    def test_custom_exceptions_tuple(self):
        """Should handle multiple exception types"""
        attempts = [0]

        def mock_func():
            attempts[0] += 1
            if attempts[0] == 1:
                raise ConnectionError("Network")
            elif attempts[0] == 2:
                raise TimeoutError("Timeout")
            else:
                return "success"

        decorated = retry_on_error(
            max_retries=3, delay=0.01, exceptions=(ConnectionError, TimeoutError)
        )(mock_func)

        result = decorated()

        assert result == "success"
        assert attempts[0] == 3


class TestSafeExecute:
    """Test suite for safe_execute wrapper"""

    def test_successful_execution(self):
        """Should return function result when successful"""
        mock_func = Mock(return_value=42)

        result = safe_execute(mock_func, default=0)

        assert result == 42
        assert mock_func.call_count == 1

    def test_exception_returns_default(self):
        """Should return default value when exception occurs"""
        mock_func = Mock(side_effect=ValueError("Error"))

        result = safe_execute(mock_func, default=999)

        assert result == 999

    def test_with_args_and_kwargs(self):
        """Should pass args and kwargs to function"""
        mock_func = Mock(return_value="result")

        result = safe_execute(
            mock_func,
            "arg1",
            "arg2",
            default="default",
            kwarg1="value1",
            kwarg2="value2",
        )

        assert result == "result"
        mock_func.assert_called_once_with(
            "arg1", "arg2", kwarg1="value1", kwarg2="value2"
        )

    def test_custom_error_message_logged(self):
        """Should log custom error message when provided"""
        mock_func = Mock(side_effect=RuntimeError("Boom"))

        with patch("consultant_toolkit.retry.logger") as mock_logger:
            result = safe_execute(
                mock_func, default=None, error_msg="Custom error occurred"
            )

            assert result is None
            # Verify logger was called with custom message
            mock_logger.error.assert_called_once()
            args = mock_logger.error.call_args[0]
            assert "Custom error occurred" in args[0]


class TestCustomExceptions:
    """Test suite for custom exception classes"""

    def test_network_error_instantiation(self):
        """Should create NetworkError with message"""
        error = NetworkError("Connection failed")
        assert str(error) == "Connection failed"
        assert isinstance(error, Exception)

    def test_api_error_instantiation(self):
        """Should create APIError with message"""
        error = APIError("API rate limit exceeded")
        assert str(error) == "API rate limit exceeded"
        assert isinstance(error, Exception)

    def test_network_error_catchable_as_exception(self):
        """NetworkError should be catchable as generic Exception"""
        try:
            raise NetworkError("Test")
        except Exception as e:
            assert isinstance(e, NetworkError)

    def test_api_error_catchable_as_exception(self):
        """APIError should be catchable as generic Exception"""
        try:
            raise APIError("Test")
        except Exception as e:
            assert isinstance(e, APIError)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
