import pytest

from audio_platform.modules.recordings.ports import UnitOfWorkFactory
from tests.contracts.recordings import (
    AudioObjectStorageContract,
    Downloader,
    PartUploader,
    RecordingUnitOfWorkContract,
    StorageRejectedPut,
)
from tests.fakes.recordings import (
    FakeAudioObjectStorage,
    InMemoryRecordingStore,
    SignedSizeMismatch,
)


class TestFakeAudioObjectStorage(AudioObjectStorageContract):
    @pytest.fixture
    def storage(self) -> FakeAudioObjectStorage:
        return FakeAudioObjectStorage()

    @pytest.fixture
    def upload_part(self, storage: FakeAudioObjectStorage) -> PartUploader:
        async def upload(url: str, data: bytes) -> str:
            try:
                return storage.put_part(url, data)
            except SignedSizeMismatch:
                raise StorageRejectedPut from None

        return upload

    @pytest.fixture
    def download(self, storage: FakeAudioObjectStorage) -> Downloader:
        async def get(url: str) -> bytes:
            return storage.get(url)

        return get


class TestInMemoryUnitOfWork(RecordingUnitOfWorkContract):
    @pytest.fixture
    def uow(self) -> UnitOfWorkFactory:
        return InMemoryRecordingStore().unit_of_work
