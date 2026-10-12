"""Task T2: Independent Merkle Root Verification.

Verifies:
1. Independent recomputation of the ledger Merkle root with a separate hashlib implementation
   across fixed leaf test cases:
   - empty leaves list
   - single leaf
   - even count (2, 4, 8 leaves)
   - odd count (3, 5, 7 leaves)
2. Exact mathematical agreement between independent calculation and compute_merkle_root() in app/session.py.
3. Cryptographic tamper evidence: altering any leaf, flipping bits, or reordering leaves changes the root.
"""

from __future__ import annotations

import hashlib
import pytest

from app.session import compute_merkle_root


def independent_merkle_root(leaves: list[str]) -> str:
    """Independent implementation of binary pairwise Merkle tree root calculation."""
    cleaned = [str(x) for x in leaves if x]
    if not cleaned:
        return hashlib.sha256(b"EMPTY_MERKLE_TREE").hexdigest()

    level = list(cleaned)
    while len(level) > 1:
        next_level = []
        for i in range(0, len(level), 2):
            left = level[i]
            right = level[i + 1] if i + 1 < len(level) else left
            pair_hash = hashlib.sha256(f"{left}:{right}".encode("utf-8")).hexdigest()
            next_level.append(pair_hash)
        level = next_level

    return level[0]


def _hash_str(val: str) -> str:
    return hashlib.sha256(val.encode("utf-8")).hexdigest()


@pytest.fixture
def fixed_leaf_hashes():
    """Deterministic leaf hashes simulating screening session block hashes."""
    return [
        _hash_str("SESSION_001_BLOCK_HASH"),
        _hash_str("SESSION_002_BLOCK_HASH"),
        _hash_str("SESSION_003_BLOCK_HASH"),
        _hash_str("SESSION_004_BLOCK_HASH"),
        _hash_str("SESSION_005_BLOCK_HASH"),
        _hash_str("SESSION_006_BLOCK_HASH"),
        _hash_str("SESSION_007_BLOCK_HASH"),
        _hash_str("SESSION_008_BLOCK_HASH"),
    ]


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

def test_merkle_empty_leaves():
    """T2: Empty leaves produces identical deterministic EMPTY_MERKLE_TREE digest."""
    independent = independent_merkle_root([])
    session_root = compute_merkle_root([])
    assert session_root == independent
    assert session_root == hashlib.sha256(b"EMPTY_MERKLE_TREE").hexdigest()


def test_merkle_single_leaf(fixed_leaf_hashes):
    """T2: Single leaf returns the leaf itself as the root."""
    leaves = [fixed_leaf_hashes[0]]
    independent = independent_merkle_root(leaves)
    session_root = compute_merkle_root(leaves)
    assert session_root == independent
    assert session_root == fixed_leaf_hashes[0]


def test_merkle_even_count(fixed_leaf_hashes):
    """T2: Even counts (2, 4, 8) compute exact matching binary pairwise roots."""
    for count in (2, 4, 8):
        leaves = fixed_leaf_hashes[:count]
        independent = independent_merkle_root(leaves)
        session_root = compute_merkle_root(leaves)
        assert session_root == independent, f"Mismatch on even count {count}"
        assert len(session_root) == 64


def test_merkle_odd_count(fixed_leaf_hashes):
    """T2: Odd counts (3, 5, 7) handle trailing duplicate leaf identically."""
    for count in (3, 5, 7):
        leaves = fixed_leaf_hashes[:count]
        independent = independent_merkle_root(leaves)
        session_root = compute_merkle_root(leaves)
        assert session_root == independent, f"Mismatch on odd count {count}"
        assert len(session_root) == 64


def test_merkle_tamper_detection(fixed_leaf_hashes):
    """T2: Tampering with any leaf in an odd or even set changes the root hash."""
    leaves = fixed_leaf_hashes[:5]
    original_root = compute_merkle_root(leaves)

    for i in range(len(leaves)):
        tampered_leaves = list(leaves)
        # Flip first character of hash
        tampered_hash = ("0" if tampered_leaves[i][0] != "0" else "1") + tampered_leaves[i][1:]
        tampered_leaves[i] = tampered_hash

        tampered_root = compute_merkle_root(tampered_leaves)
        assert tampered_root != original_root, f"Tampering at leaf {i} failed to change root hash"


def test_merkle_order_sensitivity(fixed_leaf_hashes):
    """T2: Reordering leaves changes the Merkle root (strict sequence integrity)."""
    leaves = fixed_leaf_hashes[:4]
    original_root = compute_merkle_root(leaves)

    reordered = [leaves[1], leaves[0], leaves[2], leaves[3]]
    reordered_root = compute_merkle_root(reordered)
    assert reordered_root != original_root, "Permuting leaves must alter Merkle root"
