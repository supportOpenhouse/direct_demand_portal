class ApiError(Exception):
    """Application error rendered as the contract envelope {detail, fields?}."""

    def __init__(self, status_code: int, detail: str, fields: dict[str, str] | None = None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.fields = fields
