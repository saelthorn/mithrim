import math
import random



def _decoration_hash(x, y, salt):
    """
    Deterministic pseudo-random value in [0, 1) for a tile, used to scatter
    decorations. Unlike a linear check such as `(x * a + y * b) % n == 0`,
    which always produces evenly-spaced parallel diagonal lines (an artifact
    of the congruence, not real randomness), this mixes the bits of x, y,
    and a salt so results look organically scattered while still being
    fully deterministic for a given tile/salt pair (no shared RNG state,
    safe to call in any order).
    """

    h = (x * 0x1F1F1F1F) ^ (y * 0x2545F491) ^ (salt * 0x9E3779B1)
    h = (h ^ (h >> 15)) * 0x85EBCA6B
    h = (h ^ (h >> 13)) * 0xC2B2AE35
    h ^= h >> 16

    return (h & 0xFFFFFFFF) / 0xFFFFFFFF





def _chance(x, y, salt, probability):
    """Returns True with roughly `probability` odds, scattered (not aligned)."""
    return _decoration_hash(x, y, salt) < probability



class HeightMap:
    """
    Stores the elevation of every tile.
    Values are normalized between 0.0 and 1.0.
    """

    def __init__(self, width, height):
        self.width = width
        self.height = height

        self.values = [
            [0.0 for _ in range(width)]
            for _ in range(height)
        ]

    def get(self, x, y):
        return self.values[y][x]

    def set(self, x, y, value):
        self.values[y][x] = value


def _build_permutation_table(seed):
    rng = random.Random(seed)
    perm = list(range(256))
    rng.shuffle(perm)

    return perm + perm


def _fade(t):
    return t * t * t * (t * (t * 6 - 15) + 10)


def _lerp(t, a, b):
    return a + t * (b - a)


def _gradient(hash_value, x, y):
    """Pick one of 8 gradient directions based on the low bits of the hash."""
    h = hash_value & 7
    u = x if h < 4 else y
    v = y if h < 4 else x

    return (u if h & 1 == 0 else -u) + (v if h & 2 == 0 else -v)


def _perlin(perm, x, y):
    """Sample 2D Perlin noise at (x, y). Returns a value roughly in [-1, 1]."""
    xi, yi = int(math.floor(x)) & 255, int(math.floor(y)) & 255
    xf, yf = x - math.floor(x), y - math.floor(y)
    u, v = _fade(xf), _fade(yf)

    aa = perm[perm[xi] + yi]
    ab = perm[perm[xi] + yi + 1]
    ba = perm[perm[xi + 1] + yi]
    bb = perm[perm[xi + 1] + yi + 1]


    top = _lerp(u, _gradient(aa, xf, yf), _gradient(ba, xf - 1, yf))
    bottom = _lerp(u, _gradient(ab, xf, yf - 1), _gradient(bb, xf - 1, yf - 1))

    return _lerp(v, top, bottom)


def _fractal_noise(perm, x, y, octaves, persistence, lacunarity):
    """Layer several octaves of Perlin noise (fBm) for more natural-looking detail."""
    total, amplitude, frequency, max_amplitude = 0.0, 1.0, 1.0, 0.0

    for _ in range(octaves):
        total += _perlin(perm, x * frequency, y * frequency) * amplitude
        max_amplitude += amplitude
        amplitude *= persistence
        frequency *= lacunarity

    return total / max_amplitude  # normalized back to roughly [-1, 1]