"""Narrow current-user Keychain access through Apple's native Security API.

Only an exact service/account pair is ever queried. No credential data enters
a subprocess argument, ordinary file, error message, or diagnostic log.
"""

from __future__ import annotations

from contextlib import contextmanager
import ctypes
import sys
from typing import Iterator

from app.core.desktop_llm_config import DesktopLlmConfigStoreError


MACOS_LLM_KEYCHAIN_SERVICE = "com.novwr.desktop.llm-config"
_ERR_ITEM_NOT_FOUND = -25300
_ERR_DUPLICATE_ITEM = -25299
_UTF8_ENCODING = 0x08000100


class _DictionaryKeyCallbacks(ctypes.Structure):
    _fields_ = [("version", ctypes.c_long)] + [
        (name, ctypes.c_void_p)
        for name in ("retain", "release", "copyDescription", "equal", "hash")
    ]


class _DictionaryValueCallbacks(ctypes.Structure):
    _fields_ = [("version", ctypes.c_long)] + [
        (name, ctypes.c_void_p)
        for name in ("retain", "release", "copyDescription", "equal")
    ]


class MacKeychain:
    """A local macOS generic-password item, with default OS access controls.

    The creating executable is trusted according to its code-signing identity.
    No custom allow-all ACL, access-group entitlement, or UI auto-approval is
    installed. Stable signing of the desktop sidecar preserves upgrade access.
    """

    def __init__(self, *, service: str = MACOS_LLM_KEYCHAIN_SERVICE):
        if sys.platform != "darwin":
            raise DesktopLlmConfigStoreError(
                code="desktop_llm_config_platform_unsupported",
                message="Keychain credential protection requires macOS.",
            )
        if not service or "\0" in service:
            raise ValueError("Keychain service must be non-empty and contain no NUL")
        self._service = service
        try:
            self._security = ctypes.CDLL("/System/Library/Frameworks/Security.framework/Security")
            self._cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
            self._configure_functions()
        except (OSError, AttributeError, ValueError) as exc:
            raise DesktopLlmConfigStoreError(
                code="desktop_llm_config_crypto_failed",
                message="The macOS Keychain framework is unavailable.",
            ) from exc

    def _configure_functions(self) -> None:
        pointer = ctypes.c_void_p
        self._cf.CFStringCreateWithCString.argtypes = [pointer, ctypes.c_char_p, ctypes.c_uint32]
        self._cf.CFStringCreateWithCString.restype = pointer
        self._cf.CFDataCreate.argtypes = [pointer, ctypes.c_char_p, ctypes.c_long]
        self._cf.CFDataCreate.restype = pointer
        self._cf.CFDataGetLength.argtypes = [pointer]
        self._cf.CFDataGetLength.restype = ctypes.c_long
        self._cf.CFDataGetBytePtr.argtypes = [pointer]
        self._cf.CFDataGetBytePtr.restype = pointer
        self._cf.CFDataGetTypeID.argtypes = []
        self._cf.CFDataGetTypeID.restype = ctypes.c_ulong
        self._cf.CFGetTypeID.argtypes = [pointer]
        self._cf.CFGetTypeID.restype = ctypes.c_ulong
        self._cf.CFDictionaryCreate.argtypes = [
            pointer, ctypes.POINTER(pointer), ctypes.POINTER(pointer), ctypes.c_long, pointer, pointer,
        ]
        self._cf.CFDictionaryCreate.restype = pointer
        self._cf.CFRelease.argtypes = [pointer]
        self._cf.CFRelease.restype = None
        self._key_callbacks = _DictionaryKeyCallbacks.in_dll(self._cf, "kCFTypeDictionaryKeyCallBacks")
        self._value_callbacks = _DictionaryValueCallbacks.in_dll(self._cf, "kCFTypeDictionaryValueCallBacks")
        for name in ("SecItemCopyMatching", "SecItemAdd"):
            function = getattr(self._security, name)
            function.argtypes = [pointer, ctypes.POINTER(pointer)]
            function.restype = ctypes.c_int32
        self._security.SecItemUpdate.argtypes = [pointer, pointer]
        self._security.SecItemUpdate.restype = ctypes.c_int32
        self._security.SecItemDelete.argtypes = [pointer]
        self._security.SecItemDelete.restype = ctypes.c_int32

    def _constant(self, name: str) -> ctypes.c_void_p:
        library = self._cf if name.startswith("kCF") else self._security
        return ctypes.c_void_p.in_dll(library, name)

    @staticmethod
    def _check(status: int, operation: str) -> None:
        if status:
            raise DesktopLlmConfigStoreError(
                code="desktop_llm_config_crypto_failed",
                message=f"macOS Keychain failed during {operation} (OSStatus {status}).",
            )

    @contextmanager
    def _dictionary(self, attributes: dict[str, str | bytes | ctypes.c_void_p]) -> Iterator[int]:
        owned = []
        dictionary = None
        try:
            keys, values = [], []
            for name, value in attributes.items():
                keys.append(self._constant(name))
                if isinstance(value, str):
                    reference = self._cf.CFStringCreateWithCString(None, value.encode("utf-8"), _UTF8_ENCODING)
                    owned.append(reference)
                elif isinstance(value, bytes):
                    reference = self._cf.CFDataCreate(None, value, len(value))
                    owned.append(reference)
                else:
                    reference = value.value
                if not reference:
                    self._check(-108, "allocation")  # memFullErr
                values.append(reference)
            array_type = ctypes.c_void_p * len(keys)
            dictionary = self._cf.CFDictionaryCreate(
                None, array_type(*keys), array_type(*values), len(keys),
                ctypes.byref(self._key_callbacks), ctypes.byref(self._value_callbacks),
            )
            if not dictionary:
                self._check(-108, "allocation")
            yield dictionary
        finally:
            if dictionary:
                self._cf.CFRelease(dictionary)
            for reference in reversed(owned):
                if reference:
                    self._cf.CFRelease(reference)

    def _query(self, account: str) -> dict[str, str | bytes | ctypes.c_void_p]:
        if not account or "\0" in account:
            raise ValueError("Keychain account must be non-empty and contain no NUL")
        return {
            "kSecClass": self._constant("kSecClassGenericPassword"),
            "kSecAttrService": self._service,
            "kSecAttrAccount": account,
            "kSecAttrSynchronizable": self._constant("kCFBooleanFalse"),
        }

    def read(self, account: str) -> bytes | None:
        attributes = self._query(account)
        attributes.update({
            "kSecReturnData": self._constant("kCFBooleanTrue"),
            "kSecMatchLimit": self._constant("kSecMatchLimitOne"),
        })
        output = ctypes.c_void_p()
        try:
            with self._dictionary(attributes) as query:
                status = self._security.SecItemCopyMatching(query, ctypes.byref(output))
            if status == _ERR_ITEM_NOT_FOUND:
                return None
            self._check(status, "read")
            if not output or self._cf.CFGetTypeID(output) != self._cf.CFDataGetTypeID():
                self._check(-50, "read")  # errSecParam: invalid result type
            length = self._cf.CFDataGetLength(output)
            return ctypes.string_at(self._cf.CFDataGetBytePtr(output), length)
        finally:
            if output:
                self._cf.CFRelease(output)

    def write(self, account: str, payload: bytes) -> None:
        attributes = self._query(account)
        with self._dictionary(attributes) as query, self._dictionary({"kSecValueData": payload}) as update:
            status = self._security.SecItemUpdate(query, update)
            if status == _ERR_ITEM_NOT_FOUND:
                with self._dictionary({
                    **attributes, "kSecValueData": payload, "kSecAttrLabel": "NovWr model configuration",
                }) as new_item:
                    status = self._security.SecItemAdd(new_item, None)
                if status == _ERR_DUPLICATE_ITEM:
                    # Another writer created this same profile after our read.
                    status = self._security.SecItemUpdate(query, update)
            self._check(status, "save")

    def delete(self, account: str) -> None:
        with self._dictionary(self._query(account)) as query:
            status = self._security.SecItemDelete(query)
        if status != _ERR_ITEM_NOT_FOUND:
            self._check(status, "delete")
