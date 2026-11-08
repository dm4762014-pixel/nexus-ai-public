"""Optional connector contract. No accounts, tokens or external actions assumed."""
from typing import Protocol


class Connector(Protocol):
    name: str
    required_scopes: tuple[str, ...]

    def connected(self, user_id: str) -> bool: ...

    def execute(self, user_id: str, operation: str, arguments: dict, approval_id: str) -> dict: ...


class ConnectorRegistry:
    def __init__(self):
        self._connectors = {}

    def register(self, connector: Connector):
        if connector.name in self._connectors:
            raise ValueError('Duplicate connector')
        self._connectors[connector.name] = connector

    def get(self, name, user_id):
        connector = self._connectors.get(name)
        if not connector or not connector.connected(user_id):
            raise PermissionError('Integration unavailable or not authorized')
        return connector
