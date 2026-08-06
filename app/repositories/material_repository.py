"""Contrato de persistencia para recursos didácticos."""


class MaterialRepository:
    """Encapsulate future SQLite queries for generated resources."""

    def get_by_id(self, material_id: int) -> None:
        """Retrieve a material by its primary key."""
        raise NotImplementedError

