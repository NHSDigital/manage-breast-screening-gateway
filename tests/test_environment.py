from environment import Environment


class TestEnvironment:
    def test_environment(self, monkeypatch):
        """Environment: Environment."""
        env = Environment()

        # Default should be development
        assert env.development
        assert not env.production
        assert not env.review
        assert not env.preprod

        # Test production environment
        monkeypatch.setenv("ENVIRONMENT", "prod")
        assert env.production
        assert not env.development
        assert not env.review
        assert not env.preprod

        # Test review environment
        monkeypatch.setenv("ENVIRONMENT", "review")
        assert env.review
        assert not env.development
        assert not env.production
        assert not env.preprod

        # Test preprod environment
        monkeypatch.setenv("ENVIRONMENT", "preprod")
        assert env.preprod
        assert not env.development
        assert not env.production

        # Test unknown environment defaults to development
        monkeypatch.setenv("ENVIRONMENT", "unknown")
        assert env.development
        assert not env.production
        assert not env.review
        assert not env.preprod
