import pytest

from app.services.repository_service import validate_github_url, InvalidRepositoryURLError


def test_validate_github_url_ok():
    parts = validate_github_url("https://github.com/facebook/react")
    assert parts["owner"] == "facebook"
    assert parts["repo"] == "react"


def test_validate_github_url_trailing_git():
    parts = validate_github_url("https://github.com/facebook/react.git")
    assert parts["repo"] == "react"


def test_validate_github_url_invalid():
    with pytest.raises(InvalidRepositoryURLError):
        validate_github_url("not-a-url")
