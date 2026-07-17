from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Protocol, cast

from app.core.llm_api_key import (
    LLM_API_KEY_INVALID_CODE,
    LLM_API_KEY_INVALID_MESSAGE,
    LlmApiKeyError,
    validate_llm_api_key,
)
from app.core.llm_endpoint import OpenAIBaseUrlError, normalize_openai_base_url


DESKTOP_LLM_CONFIG_SCHEMA_VERSION = 1
_CRYPTPROTECT_UI_FORBIDDEN = 0x1
_DPAPI_DESCRIPTION = "NovWr desktop LLM configuration"


class DesktopLlmConfigStoreError(RuntimeError):
    def __init__(self, *, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class StoredDesktopLlmConfig:
    base_url: str
    api_key: str = field(repr=False)
    model: str


class DataProtector(Protocol):
    def protect(self, plaintext: bytes) -> bytes: ...

    def unprotect(self, ciphertext: bytes) -> bytes: ...


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


class WindowsDataProtector:
    """Current-user Windows DPAPI adapter."""

    def __init__(self, *, crypt32=None, kernel32=None):
        if sys.platform != "win32" and (crypt32 is None or kernel32 is None):
            raise DesktopLlmConfigStoreError(
                code="desktop_llm_config_platform_unsupported",
                message="Desktop LLM credential protection requires Windows.",
            )
        self._crypt32 = crypt32 or ctypes.WinDLL("crypt32", use_last_error=True)
        self._kernel32 = kernel32 or ctypes.WinDLL("kernel32", use_last_error=True)
        self._configure_functions()

    def _configure_functions(self) -> None:
        self._crypt32.CryptProtectData.argtypes = [
            ctypes.POINTER(_DataBlob),
            wintypes.LPCWSTR,
            ctypes.POINTER(_DataBlob),
            wintypes.LPVOID,
            wintypes.LPVOID,
            wintypes.DWORD,
            ctypes.POINTER(_DataBlob),
        ]
        self._crypt32.CryptProtectData.restype = wintypes.BOOL
        self._crypt32.CryptUnprotectData.argtypes = [
            ctypes.POINTER(_DataBlob),
            ctypes.POINTER(wintypes.LPWSTR),
            ctypes.POINTER(_DataBlob),
            wintypes.LPVOID,
            wintypes.LPVOID,
            wintypes.DWORD,
            ctypes.POINTER(_DataBlob),
        ]
        self._crypt32.CryptUnprotectData.restype = wintypes.BOOL
        self._kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
        self._kernel32.LocalFree.restype = wintypes.HLOCAL

    @staticmethod
    def _blob(data: bytes) -> tuple[_DataBlob, object]:
        buffer = ctypes.create_string_buffer(data)
        blob = _DataBlob(
            cbData=len(data),
            pbData=ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)),
        )
        return blob, buffer

    def _copy_and_free(self, output: _DataBlob) -> bytes:
        if not output.pbData:
            return b""
        try:
            return ctypes.string_at(output.pbData, output.cbData)
        finally:
            self._kernel32.LocalFree(ctypes.cast(output.pbData, wintypes.HLOCAL))

    @staticmethod
    def _windows_error(operation: str) -> DesktopLlmConfigStoreError:
        error_code = ctypes.get_last_error()
        return DesktopLlmConfigStoreError(
            code="desktop_llm_config_crypto_failed",
            message=f"Windows credential protection failed during {operation} (error {error_code}).",
        )

    def protect(self, plaintext: bytes) -> bytes:
        input_blob, input_buffer = self._blob(plaintext)
        output_blob = _DataBlob()
        _ = input_buffer
        ok = self._crypt32.CryptProtectData(
            ctypes.byref(input_blob),
            _DPAPI_DESCRIPTION,
            None,
            None,
            None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(output_blob),
        )
        if not ok:
            raise self._windows_error("encryption")
        return self._copy_and_free(output_blob)

    def unprotect(self, ciphertext: bytes) -> bytes:
        input_blob, input_buffer = self._blob(ciphertext)
        output_blob = _DataBlob()
        description = wintypes.LPWSTR()
        _ = input_buffer
        ok = self._crypt32.CryptUnprotectData(
            ctypes.byref(input_blob),
            ctypes.byref(description),
            None,
            None,
            None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(output_blob),
        )
        if not ok:
            raise self._windows_error("decryption")
        try:
            return self._copy_and_free(output_blob)
        finally:
            if description:
                self._kernel32.LocalFree(ctypes.cast(description, wintypes.HLOCAL))


class DesktopLlmConfigStore:
    def __init__(self, path: Path, *, protector: DataProtector):
        self.path = Path(path)
        self._protector = protector

    def load(self) -> StoredDesktopLlmConfig | None:
        try:
            raw = self.path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise DesktopLlmConfigStoreError(
                code="desktop_llm_config_read_failed",
                message=f"Unable to read the desktop LLM configuration at {self.path}.",
            ) from exc

        try:
            envelope = json.loads(raw)
            if not isinstance(envelope, dict):
                raise ValueError("envelope must be an object")
            if envelope.get("version") != DESKTOP_LLM_CONFIG_SCHEMA_VERSION:
                raise ValueError("unsupported envelope version")
            encoded = envelope.get("ciphertext")
            if not isinstance(encoded, str) or not encoded:
                raise ValueError("ciphertext is missing")
            ciphertext = base64.b64decode(encoded, validate=True)
            payload = json.loads(self._protector.unprotect(ciphertext))
            if not isinstance(payload, dict):
                raise ValueError("payload must be an object")
            if payload.get("version") != DESKTOP_LLM_CONFIG_SCHEMA_VERSION:
                raise ValueError("unsupported payload version")
            config = self._normalize_config(
                StoredDesktopLlmConfig(
                    base_url=str(payload.get("base_url") or ""),
                    api_key=cast(str, payload.get("api_key")),
                    model=str(payload.get("model") or ""),
                )
            )
        except DesktopLlmConfigStoreError:
            raise
        except Exception as exc:
            raise DesktopLlmConfigStoreError(
                code="desktop_llm_config_unreadable",
                message="The saved desktop LLM configuration is invalid or unreadable.",
            ) from exc

        return config

    @staticmethod
    def _normalize_config(config: StoredDesktopLlmConfig) -> StoredDesktopLlmConfig:
        raw_base_url = str(config.base_url or "")
        raw_api_key = config.api_key
        model = str(config.model or "").strip()
        if not raw_base_url.strip() or not model:
            raise DesktopLlmConfigStoreError(
                code="desktop_llm_config_invalid",
                message="Desktop LLM configuration requires base URL, API key, and model.",
            )
        try:
            api_key = validate_llm_api_key(raw_api_key)
        except LlmApiKeyError as exc:
            raise DesktopLlmConfigStoreError(
                code=LLM_API_KEY_INVALID_CODE,
                message=LLM_API_KEY_INVALID_MESSAGE,
            ) from exc
        if not api_key:
            raise DesktopLlmConfigStoreError(
                code="desktop_llm_config_invalid",
                message="Desktop LLM configuration requires base URL, API key, and model.",
            )
        try:
            base_url = normalize_openai_base_url(raw_base_url)
        except OpenAIBaseUrlError as exc:
            raise DesktopLlmConfigStoreError(
                code="desktop_llm_config_invalid",
                message="Desktop LLM configuration contains an invalid base URL.",
            ) from exc
        return StoredDesktopLlmConfig(
            base_url=base_url,
            api_key=api_key,
            model=model,
        )

    def save(self, config: StoredDesktopLlmConfig) -> None:
        normalized = self._normalize_config(config)
        payload = json.dumps(
            {
                "version": DESKTOP_LLM_CONFIG_SCHEMA_VERSION,
                "base_url": normalized.base_url,
                "api_key": normalized.api_key,
                "model": normalized.model,
            },
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
        ciphertext = self._protector.protect(payload)
        serialized = (
            json.dumps(
                {
                    "version": DESKTOP_LLM_CONFIG_SCHEMA_VERSION,
                    "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
                },
                ensure_ascii=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")

        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary_name = tempfile.mkstemp(
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
            )
            temporary_path = Path(temporary_name)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(serialized)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary_path, self.path)
            except Exception:
                temporary_path.unlink(missing_ok=True)
                raise
        except DesktopLlmConfigStoreError:
            raise
        except OSError as exc:
            raise DesktopLlmConfigStoreError(
                code="desktop_llm_config_write_failed",
                message=f"Unable to save the desktop LLM configuration at {self.path}.",
            ) from exc

    def delete(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError as exc:
            raise DesktopLlmConfigStoreError(
                code="desktop_llm_config_delete_failed",
                message=f"Unable to delete the desktop LLM configuration at {self.path}.",
            ) from exc
