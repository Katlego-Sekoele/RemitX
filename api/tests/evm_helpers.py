"""A throwaway EVM treasury wallet, configured the way the setup script does it."""

from dataclasses import dataclass

from cryptography.fernet import Fernet
from eth_account import Account


@dataclass(frozen=True)
class FakeTreasury:
    address: str
    private_key: str  # 0x-prefixed hex, as create_evm_platform_wallet.py writes it
    encryption_key: str
    encrypted_key: str

    @property
    def secrets(self) -> tuple[str, str, str]:
        """Every value that must never leave the worker."""
        return (self.private_key, self.encrypted_key, self.encryption_key)


def configure_fake_treasury(monkeypatch) -> FakeTreasury:
    """Put a fresh random treasury wallet into the environment."""
    account = Account.create()
    private_key = "0x" + bytes(account.key).hex()
    encryption_key = Fernet.generate_key().decode()
    fernet = Fernet(encryption_key.encode())
    encrypted_key = fernet.encrypt(private_key.encode()).decode()

    monkeypatch.setenv("EVM_TREASURY_ADDRESS", account.address)
    monkeypatch.setenv("EVM_ENCRYPTION_KEY", encryption_key)
    monkeypatch.setenv("EVM_TREASURY_KEY_ENCRYPTED", encrypted_key)
    return FakeTreasury(account.address, private_key, encryption_key, encrypted_key)
