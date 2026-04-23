import json

import pytest

from src.core.types import (
    Chunk,
    ChunkRecord,
    Document,
    extract_image_ids_from_text,
    format_image_placeholder,
    to_json,
    validate_chunk_contract,
    validate_document_contract,
    validate_images_metadata,
    validate_metadata_source_path,
)


def test_document_roundtrip_dict_and_json():
    doc = Document(
        id="doc-1",
        text="Hello",
        metadata={"source_path": "/tmp/a.pdf", "title": "A"},
    )
    d = doc.to_dict()
    assert d == {
        "id": "doc-1",
        "text": "Hello",
        "metadata": {"source_path": "/tmp/a.pdf", "title": "A"},
    }
    back = Document.from_dict(d)
    assert back == doc
    json.loads(to_json(doc))  # stable JSON


def test_chunk_roundtrip_optional_source_ref():
    ch = Chunk(
        id="c1",
        text="chunk",
        metadata={"source_path": "/x.pdf", "chunk_index": 0},
        start_offset=0,
        end_offset=5,
        source_ref="doc-1",
    )
    payload = ch.to_dict()
    assert payload["source_ref"] == "doc-1"
    ch2 = Chunk.from_dict(payload)
    assert ch2 == ch

    ch_none = Chunk(
        id="c2",
        text="b",
        metadata={"source_path": "/y.pdf"},
        start_offset=0,
        end_offset=1,
        source_ref=None,
    )
    assert "source_ref" not in ch_none.to_dict()
    assert Chunk.from_dict(ch_none.to_dict()).source_ref is None


def test_chunk_record_vectors_roundtrip():
    rec = ChunkRecord(
        id="r1",
        text="t",
        metadata={"source_path": "/z.pdf"},
        dense_vector=[0.1, 0.2],
        sparse_vector={"a": 1.0, "b": 2.0},
    )
    rec2 = ChunkRecord.from_dict(rec.to_dict())
    assert rec2.dense_vector == [0.1, 0.2]
    assert rec2.sparse_vector == {"a": 1.0, "b": 2.0}

    minimal = ChunkRecord(id="r2", text="x", metadata={"source_path": "/p"})
    assert ChunkRecord.from_dict(minimal.to_dict()) == minimal


def test_validate_metadata_requires_source_path():
    with pytest.raises(ValueError, match="source_path"):
        validate_metadata_source_path({})
    with pytest.raises(ValueError, match="source_path"):
        validate_metadata_source_path({"source_path": ""})


def test_validate_images_metadata():
    good = [
        {
            "id": "h_p_0",
            "path": "data/images/col/h_p_0.png",
            "page": 1,
            "text_offset": 10,
            "text_length": len(format_image_placeholder("h_p_0")),
            "position": {"x0": 0},
        }
    ]
    validate_images_metadata(good)
    validate_images_metadata(None)

    with pytest.raises(ValueError, match="must be a list"):
        validate_images_metadata({})

    with pytest.raises(ValueError, match="missing required"):
        validate_images_metadata([{"id": "x"}])


def test_validate_document_contract_with_images():
    iid = "abc_1_0"
    ph = format_image_placeholder(iid)
    doc = Document(
        id="d",
        text=f"pre {ph} post",
        metadata={
            "source_path": "/f.pdf",
            "images": [
                {
                    "id": iid,
                    "path": f"data/images/c/{iid}.png",
                    "page": 1,
                    "text_offset": 4,
                    "text_length": len(ph),
                }
            ],
        },
    )
    validate_document_contract(doc)
    assert extract_image_ids_from_text(doc.text) == [iid]


def test_image_placeholder_format():
    assert format_image_placeholder("x_y_1") == "[IMAGE: x_y_1]"
    assert extract_image_ids_from_text("a [IMAGE: id1] b [IMAGE: id2]") == ["id1", "id2"]


def test_from_dict_type_errors():
    with pytest.raises(TypeError, match="metadata"):
        Document.from_dict({"id": "1", "text": "t", "metadata": "bad"})
    with pytest.raises(TypeError, match="dense_vector"):
        ChunkRecord.from_dict(
            {
                "id": "1",
                "text": "t",
                "metadata": {"source_path": "/a"},
                "dense_vector": "nope",
            }
        )


def test_validate_chunk_contract():
    c = Chunk(
        id="c",
        text="x",
        metadata={"source_path": "/s", "images": []},
        start_offset=0,
        end_offset=1,
    )
    validate_chunk_contract(c)
