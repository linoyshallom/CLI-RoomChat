import dataclasses

@dataclasses.dataclass(frozen=True)
class ClientConfig:
    allowed_input_user_pattern: str = "/^[a-zA-Z0-9._]+$/"   #.*"
