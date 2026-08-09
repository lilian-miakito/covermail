"""FastAPI application wired directly to the Covermail protocol and MLX codec."""

from __future__ import annotations

import asyncio
import copy
import ipaddress
import json
import math
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from starlette.middleware.base import RequestResponseEndpoint

from covermail.address.canonical import load_address_json
from covermail.address.fingerprint import human_fingerprint, machine_address_id
from covermail.address.schema import Address, validate_address
from covermail.codec.carrier import decode_carrier, encode_carrier
from covermail.codec.generative import CarrierDecodeProgress, CarrierTokenEvent
from covermail.cover.transport import canonical_carrier
from covermail.crypto.hpke import HPKE_ENCAPSULATED_KEY_BYTES, HPKE_TAG_BYTES
from covermail.crypto.identity import generate_identity
from covermail.crypto.private_store import load_identity_address, save_identity, unlock_identity
from covermail.errors import CovermailError
from covermail.models.mlx_adapter import MODEL_ID, MODEL_REVISION, MlxLanguageModel
from covermail.models.profile import LoadedProfile, load_profile
from covermail.protocol.inner_frame import FLAG_DEFLATE, pack_inner
from covermail.protocol.varint import decode_uvarint
from covermail.service import METADATA_CAPSULE_BYTES
from covermail.web.jobs import Job, JobManager

API_PREFIX = "/api/v1"
MAX_REQUEST_BYTES = 1 << 20
MAX_CARRIER_CHARACTERS = 200_000
ESTIMATED_TOKENS_PER_STREAM_BYTE = 3.2
ESTIMATED_CHARACTERS_PER_STREAM_BYTE = 13.5
ProfileLoader = Callable[[Address, Path, str, MlxLanguageModel | None], LoadedProfile]


@dataclass(frozen=True, slots=True)
class AppConfig:
    model_root: Path
    identities_dir: Path
    host: str = "127.0.0.1"
    port: int = 8765
    template_path: Path | None = None

    @property
    def origin(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"http://{host}:{self.port}"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class IdentityCreateRequest(StrictModel):
    label: str = Field(min_length=1, max_length=128)
    passphrase: SecretStr = Field(min_length=1, max_length=1024)
    passphrase_confirmation: SecretStr = Field(min_length=1, max_length=1024)


class AddressRequest(StrictModel):
    address: dict[str, Any]


class EstimateRequest(AddressRequest):
    prompt: str = Field(min_length=1, max_length=4096)
    secret: str = Field(max_length=65_535)


class EncodeRequest(EstimateRequest):
    fingerprint_confirmed: bool
    live_preview: bool = True


class DecodeRequest(StrictModel):
    identity_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    passphrase: SecretStr = Field(min_length=1, max_length=1024)
    carrier: str = Field(min_length=1, max_length=MAX_CARRIER_CHARACTERS)


def _default_template() -> Address:
    resource = Path(__file__).with_name("profile.json")
    return validate_address(load_address_json(resource.read_bytes()))


def _template(config: AppConfig) -> Address:
    if config.template_path is None:
        return _default_template()
    return validate_address(load_address_json(config.template_path.read_bytes()))


def _artifact_key(address: Address) -> str:
    model = cast(dict[str, Any], address["model"])
    return json.dumps(model["artifacts"], sort_keys=True, separators=(",", ":"))


class LocalModel:
    """Keep one verified MLX adapter resident while binding fresh visible contexts."""

    def __init__(self, root: Path, loader: ProfileLoader) -> None:
        self.root = root
        self.loader = loader
        self.adapter: MlxLanguageModel | None = None
        self.artifact_key: str | None = None

    def bind(self, address: Address, writing_brief: str = "") -> LoadedProfile:
        key = _artifact_key(address)
        reusable = self.adapter if self.artifact_key == key else None
        loaded = self.loader(address, self.root, writing_brief, reusable)
        adapter = getattr(loaded.payload_model, "adapter", None)
        if isinstance(adapter, MlxLanguageModel):
            self.adapter = adapter
            self.artifact_key = key
        return loaded


def _profile_loader(
    address: Address,
    root: Path,
    writing_brief: str,
    adapter: MlxLanguageModel | None,
) -> LoadedProfile:
    return load_profile(address, root, writing_brief, adapter=adapter)


def _identity_path(config: AppConfig, identity_id: str) -> Path:
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
    if not identity_id or any(character not in alphabet for character in identity_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Local identity not found.")
    path = config.identities_dir / identity_id
    if path.parent != config.identities_dir or path.is_symlink() or not path.is_dir():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Local identity not found.")
    return path


def _address_summary(address: Address) -> dict[str, Any]:
    recipient = cast(dict[str, Any], address["recipient"])
    model = cast(dict[str, Any], address["model"])
    cover = cast(dict[str, Any], address["cover"])
    return {
        "address_id": machine_address_id(address),
        "fingerprint": human_fingerprint(address),
        "label": recipient["label"],
        "model_id": model["model_id"],
        "model_revision": model["revision"],
        "language": cover["language"],
        "tone": cover["tone"],
    }


def _require_supported_address(address: Address, template: Address) -> None:
    """The normal UI accepts only its one exact, locally qualified profile."""
    if address["model"] != template["model"] or address["codec"] != template["codec"]:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "This address does not match the model profile supported by this application.",
        )


def _list_identities(config: AppConfig) -> list[dict[str, Any]]:
    config.identities_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    values: list[dict[str, Any]] = []
    for path in sorted(config.identities_dir.iterdir(), key=lambda item: item.name):
        if not path.is_dir() or path.is_symlink():
            continue
        try:
            address = load_identity_address(path)
        except CovermailError:
            continue
        values.append(_address_summary(address))
    return values


def _safe_error_response(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=status_code)


def _install_local_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def local_security(request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method in {"POST", "PUT", "PATCH"}:
            content_type = request.headers.get("content-type", "").split(";", 1)[0].strip()
            if content_type != "application/json":
                return _safe_error_response(
                    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    "This API accepts JSON only.",
                )
            declared = request.headers.get("content-length")
            if declared is not None:
                try:
                    if int(declared) > MAX_REQUEST_BYTES:
                        return _safe_error_response(
                            status.HTTP_413_CONTENT_TOO_LARGE, "Request is too large."
                        )
                except ValueError:
                    return _safe_error_response(status.HTTP_400_BAD_REQUEST, "Invalid size.")
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > MAX_REQUEST_BYTES:
                    return _safe_error_response(
                        status.HTTP_413_CONTENT_TOO_LARGE, "Request is too large."
                    )
            # BaseHTTPMiddleware's call_next reuses Request.wrapped_receive. Supplying
            # the bounded body here lets the downstream parser consume exactly once.
            request._body = bytes(body)

        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
            "form-action 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        if request.url.path.startswith(API_PREFIX):
            response.headers["Cache-Control"] = "no-store"
        return response


def _sse(event: dict[str, Any]) -> bytes:
    payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    return f"id: {event['id']}\nevent: {event['type']}\ndata: {payload}\n\n".encode()


def create_app(
    config: AppConfig,
    *,
    profile_loader: ProfileLoader = _profile_loader,
) -> FastAPI:
    """Create one loopback-only local application instance."""
    jobs = JobManager()
    local_model = LocalModel(config.model_root, profile_loader)
    address_template = _template(config)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        jobs.shutdown()

    app = FastAPI(
        title="Covermail local",
        version="1",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.jobs = jobs
    _install_local_middleware(app)
    static_root = Path(__file__).with_name("static")

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, error: RequestValidationError) -> JSONResponse:
        sanitized = [
            {"path": [str(part) for part in item["loc"]], "message": item["msg"]}
            for item in error.errors()
        ]
        return JSONResponse({"detail": "Invalid input.", "errors": sanitized}, status_code=422)

    @app.exception_handler(CovermailError)
    async def covermail_error(_: Request, error: CovermailError) -> JSONResponse:
        return _safe_error_response(status.HTTP_400_BAD_REQUEST, str(error))

    @app.get("/", response_class=FileResponse)
    async def index() -> FileResponse:
        return FileResponse(static_root / "index.html")

    @app.get("/app.js", response_class=FileResponse)
    async def javascript() -> FileResponse:
        return FileResponse(static_root / "app.js", media_type="text/javascript")

    @app.get("/app.css", response_class=FileResponse)
    async def stylesheet() -> FileResponse:
        return FileResponse(static_root / "app.css", media_type="text/css")

    @app.get(f"{API_PREFIX}/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "local_only": True,
            "model_id": MODEL_ID,
            "revision": MODEL_REVISION,
        }

    @app.get(f"{API_PREFIX}/identities")
    async def identities() -> dict[str, Any]:
        return {"identities": _list_identities(config)}

    @app.get(f"{API_PREFIX}/identities/{{identity_id}}/address")
    async def identity_address(identity_id: str) -> dict[str, Any]:
        address = load_identity_address(_identity_path(config, identity_id))
        return {"address": address, **_address_summary(address)}

    @app.post(f"{API_PREFIX}/identities", status_code=status.HTTP_201_CREATED)
    async def create_identity(request: IdentityCreateRequest) -> dict[str, Any]:
        passphrase = request.passphrase.get_secret_value()
        if passphrase != request.passphrase_confirmation.get_secret_value():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Passphrases do not match.")
        template = copy.deepcopy(address_template)
        cast(dict[str, Any], template["recipient"])["label"] = request.label
        address, private_key = generate_identity(template)
        save_identity(config.identities_dir, address, private_key, passphrase)
        return {"address": address, **_address_summary(address)}

    @app.post(f"{API_PREFIX}/addresses/inspect")
    async def inspect_address(request: AddressRequest) -> dict[str, Any]:
        address = validate_address(request.address)
        _require_supported_address(address, address_template)
        return {"address": address, **_address_summary(address)}

    @app.get(f"{API_PREFIX}/models/status")
    async def model_status() -> dict[str, Any]:
        model_fields = cast(dict[str, Any], address_template["model"])
        artifacts = cast(list[dict[str, Any]], model_fields["artifacts"])
        present = sum((config.model_root / item["path"]).is_file() for item in artifacts)
        return {
            "model_id": MODEL_ID,
            "revision": MODEL_REVISION,
            "artifacts_present": present,
            "artifacts_total": len(artifacts),
            "ready_on_disk": present == len(artifacts),
            "loaded": local_model.adapter is not None,
        }

    @app.post(f"{API_PREFIX}/messages/estimate")
    async def estimate(request: EstimateRequest) -> dict[str, Any]:
        address = validate_address(request.address)
        _require_supported_address(address, address_template)
        inner = pack_inner(request.secret)
        original_bytes, varint_bytes = decode_uvarint(inner, 18, max_bytes=3)
        compressed_bytes = len(inner) - 18 - varint_bytes
        hpke_overhead = 2 * (HPKE_ENCAPSULATED_KEY_BYTES + HPKE_TAG_BYTES)
        body_capsule_bytes = len(inner) + HPKE_ENCAPSULATED_KEY_BYTES + HPKE_TAG_BYTES
        packet_bytes = METADATA_CAPSULE_BYTES + body_capsule_bytes
        return {
            "plaintext_utf8_bytes": original_bytes,
            "compressed_body_bytes": compressed_bytes,
            "compression_used": bool(inner[1] & FLAG_DEFLATE),
            "hpke_overhead_bytes": hpke_overhead,
            "metadata_capsule_bytes": METADATA_CAPSULE_BYTES,
            "body_capsule_bytes": body_capsule_bytes,
            "packet_bytes": packet_bytes,
            "estimated_carrier_tokens": math.ceil(packet_bytes * ESTIMATED_TOKENS_PER_STREAM_BYTE),
            "estimated_characters": math.ceil(packet_bytes * ESTIMATED_CHARACTERS_PER_STREAM_BYTE),
            "basis": "current accepted A/B/C/D qualification profile",
        }

    def encode_work(request: EncodeRequest) -> Callable[[Job], dict[str, Any]]:
        address = validate_address(request.address)
        _require_supported_address(address, address_template)
        if not request.fingerprint_confirmed:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Confirm the recipient fingerprint.",
            )

        def work(job: Job) -> dict[str, Any]:
            started = time.perf_counter()
            job.transition("loading_model")
            loaded = local_model.bind(address, request.prompt)
            job.emit("self_test", sha256=loaded.self_test.sha256)
            job.transition("generating")
            annotations: list[dict[str, Any]] = []
            previous_confirmed = 0
            metadata_bits = METADATA_CAPSULE_BYTES * 8

            def token(event: CarrierTokenEvent) -> None:
                nonlocal previous_confirmed
                job.check_cancelled()
                confirmed_from = previous_confirmed
                confirmed_to = event.confirmed_bits
                if event.phase == "prefix":
                    section = "A"
                    confirmed_from = confirmed_to = 0
                elif event.phase == "finish":
                    section = "D"
                    confirmed_from = confirmed_to = previous_confirmed
                elif confirmed_from < metadata_bits < confirmed_to:
                    section = "BC"
                elif confirmed_from < metadata_bits:
                    section = "B"
                else:
                    section = "C"
                if event.phase in {"metadata", "body"}:
                    previous_confirmed = confirmed_to
                annotation = {
                    "token_id": event.token_id,
                    "text": event.text,
                    "token_index": event.token_index,
                    "section": section,
                    "confirmed_from": confirmed_from,
                    "confirmed_to": confirmed_to,
                }
                annotations.append(annotation)
                payload: dict[str, Any] = {
                    "phase": event.phase,
                    "section": section,
                    "token_index": event.token_index,
                    "token_id": event.token_id,
                    "confirmed_from": confirmed_from,
                    "confirmed_bits": event.confirmed_bits,
                    "total_bits": event.total_bits,
                }
                if request.live_preview:
                    payload["delta"] = event.text
                job.emit("token", **payload)

            codec = cast(dict[str, Any], address["codec"])
            cover = cast(dict[str, Any], address["cover"])
            result = encode_carrier(
                request.secret,
                loaded.prefix_model,
                loaded.payload_model,
                loaded.finish_model,
                address,
                prefix_tokens=codec["prefix_tokens"],
                maximum_characters=cover["max_visible_characters"],
                on_token=token,
            )
            job.transition("validating")
            elapsed = time.perf_counter() - started
            packet_bytes = len(result.metadata) + len(result.body)
            return {
                "carrier": result.text,
                "packet_bytes": packet_bytes,
                "characters": len(result.text),
                "utf8_bytes": len(result.text.encode("utf-8")),
                "tokens": len(result.token_ids),
                "k_all": len(result.text) / packet_bytes,
                "elapsed_seconds": elapsed,
                "tokens_per_second": len(result.token_ids) / elapsed,
                "metrics": asdict(result.metrics),
                "token_annotations": annotations,
            }

        return work

    @app.post(f"{API_PREFIX}/messages/encode", status_code=status.HTTP_202_ACCEPTED)
    async def encode(request: EncodeRequest) -> dict[str, Any]:
        try:
            job = jobs.submit("encode", encode_work(request))
        except RuntimeError as error:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(error)) from error
        return {"job_id": job.id, "state": job.state}

    def decode_work(request: DecodeRequest) -> Callable[[Job], dict[str, Any]]:
        identity_path = _identity_path(config, request.identity_id)
        address = load_identity_address(identity_path)
        carrier = canonical_carrier(request.carrier)

        def work(job: Job) -> dict[str, Any]:
            started = time.perf_counter()
            job.transition("unlocking")
            _, private_key = unlock_identity(identity_path, request.passphrase.get_secret_value())
            job.transition("loading_model")
            loaded = local_model.bind(address)
            job.emit("self_test", sha256=loaded.self_test.sha256)
            job.transition("decoding")

            def progress(event: CarrierDecodeProgress) -> None:
                job.check_cancelled()
                job.emit(
                    "progress",
                    processed_tokens=event.processed_tokens,
                    total_tokens=event.total_tokens,
                    phase=event.phase,
                    recovered_bits=event.recovered_bits,
                    target_bits=event.target_bits,
                )

            codec = cast(dict[str, Any], address["codec"])
            cover = cast(dict[str, Any], address["cover"])
            decoded = decode_carrier(
                carrier,
                loaded.payload_model,
                address,
                private_key,
                prefix_tokens=codec["prefix_tokens"],
                maximum_characters=cover["max_visible_characters"],
                on_token=progress,
            )
            return {
                "secret": decoded.secret,
                "plaintext_utf8_bytes": len(decoded.secret.encode("utf-8")),
                "consumed_tokens": decoded.carrier.consumed_tokens,
                "ignored_finish_tokens": (
                    decoded.carrier.total_tokens - decoded.carrier.consumed_tokens
                ),
                "elapsed_seconds": time.perf_counter() - started,
            }

        return work

    @app.post(f"{API_PREFIX}/messages/decode", status_code=status.HTTP_202_ACCEPTED)
    async def decode(request: DecodeRequest) -> dict[str, Any]:
        try:
            job = jobs.submit("decode", decode_work(request))
        except RuntimeError as error:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(error)) from error
        return {"job_id": job.id, "state": job.state}

    def require_job(job_id: str) -> Job:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Job local introuvable.")
        return job

    @app.get(f"{API_PREFIX}/jobs/{{job_id}}")
    async def get_job(job_id: str) -> dict[str, Any]:
        return require_job(job_id).public()

    @app.get(f"{API_PREFIX}/jobs/{{job_id}}/events")
    async def job_events(
        job_id: str,
        cursor: int = Query(default=0, ge=0),
    ) -> StreamingResponse:
        job = require_job(job_id)

        async def stream() -> AsyncIterator[bytes]:
            position = cursor
            while True:
                events, terminal = await asyncio.to_thread(job.wait, position, 15.0)
                if not events:
                    if terminal:
                        return
                    yield b": keepalive\n\n"
                    continue
                for event in events:
                    yield _sse(event)
                    position += 1
                if terminal and position >= len(job.events):
                    return

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.delete(f"{API_PREFIX}/jobs/{{job_id}}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_job(job_id: str) -> Response:
        if not jobs.discard(job_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Job local introuvable.")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return app


def run_local_app(config: AppConfig) -> None:
    """Run the loopback-only Uvicorn application without access logs."""
    try:
        address = ipaddress.ip_address(config.host)
    except ValueError as error:
        raise ValueError("the local app host must be a loopback IP literal") from error
    if not address.is_loopback:
        raise ValueError("the local app refuses non-loopback binding")
    if not 1 <= config.port <= 65_535:
        raise ValueError("the local app port is outside 1..65535")
    app = create_app(config)
    print(f"Covermail local : {config.origin}/", flush=True)
    import uvicorn

    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        access_log=False,
        log_level="warning",
    )
