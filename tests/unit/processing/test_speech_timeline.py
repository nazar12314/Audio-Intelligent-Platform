import pytest

from audio_platform.modules.processing.domain import (
    SpeechSegment,
    SpeechTimeline,
    Transcript,
    TranscriptSegment,
    Word,
    speech_windows,
    transcript_segments,
    unheard_window_ends,
)

S = SpeechSegment


def test_consecutive_speech_is_packed_into_windows_of_at_most_20_s() -> None:
    speech = [S(1000, 9000), S(9500, 15000), S(18000, 21000), S(60000, 61000)]

    assert speech_windows(speech) == [S(1000, 21000), S(60000, 61000)]


def test_a_segment_longer_than_a_window_is_cut_into_equal_pieces() -> None:
    assert speech_windows([S(0, 1000), S(2000, 50000)]) == [
        S(0, 18000),  # the first piece still fits with the speech before it
        S(18000, 34000),
        S(34000, 50000),
    ]
    assert speech_windows([]) == []


# 1000-2000 and 2500-3000 share a window; 40000-40500 has its own.
SPEECH = [S(1000, 2000), S(2500, 3000), S(40000, 40500)]
TIMELINE = SpeechTimeline(speech_windows(SPEECH))


def test_windows_play_back_to_back() -> None:
    assert TIMELINE.window_offsets_ms() == [(0, 2000), (2000, 2500)]
    assert TIMELINE.duration_ms == 2500


@pytest.mark.parametrize(
    ("heard", "recording"),
    [
        ((0, 1000), (1000, 2000)),
        ((200, 700), (1200, 1700)),
        ((1500, 1900), (2500, 2900)),  # the pause inside a window is kept
        # A span belongs to the window holding its middle, clamped to it.
        ((1960, 2500), (40000, 40500)),
        ((2000, 2600), (40000, 40500)),
    ],
)
def test_spans_map_back_to_the_recording(
    heard: tuple[float, float], recording: tuple[int, int]
) -> None:
    assert TIMELINE.to_recording_span(*heard) == recording


def test_words_can_be_pinned_to_their_segment_window() -> None:
    # 2 ms before the second window's start: on its own it lands in the first one.
    assert TIMELINE.to_recording_span(1998, 1999) == (2998, 2999)
    assert TIMELINE.to_recording_span(1998, 1999, window=1) == (40000, 40000)
    assert TIMELINE.window_of(1800, 2500) == 1  # its middle, 2150, is past 2000


def test_an_empty_timeline_cannot_map() -> None:
    with pytest.raises(ValueError, match="no speech"):
        SpeechTimeline([]).to_recording_span(0, 1)


def w(start: int, end: int, text: str) -> Word:
    return Word(start, end, text, 0.9)


# "The smallest moments are the ones we remember. A familiar voice, a shared laugh,
# a little good news." over four speech segments (pauses of 708, 548 and 516 ms).
PHRASES = [S(1506, 4446), S(5154, 6430), S(6978, 8126), S(8642, 10031)]
FIRST = [w(1506, 1786, " The"), w(3626, 4266, " remember.")]
SECOND = [
    w(5266, 5446, " A"),
    w(5886, 6406, " voice,"),
    w(7106, 7346, " a"),
    w(7586, 8000, " laugh,"),
    w(8786, 8906, " a"),
    w(9406, 9906, " news."),
]


def test_segments_join_until_a_sentence_ends() -> None:
    assert transcript_segments(PHRASES, FIRST + SECOND) == [
        TranscriptSegment(1506, 4446, "The remember.", FIRST),
        TranscriptSegment(5154, 10031, "A voice, a laugh, a news.", SECOND),
    ]


@pytest.mark.parametrize("end", ['"Hi."', "Hi?)", "Hi\u2026", "\u4f60\u597d\u3002"])
def test_quotes_brackets_and_cjk_marks_end_sentences(end: str) -> None:
    speech = [S(0, 1000), S(1100, 2000)]
    words = [w(100, 900, f" {end}"), w(1200, 1800, " Next.")]

    assert len(transcript_segments(speech, words)) == 2


def test_a_long_pause_ends_a_segment_even_mid_sentence() -> None:
    speech = [S(0, 1000), S(2600, 3000)]
    words = [w(100, 900, " and then"), w(2700, 2900, " more.")]

    assert [s.text for s in transcript_segments(speech, words)] == ["and then", "more."]


def test_a_sentence_spoken_in_one_segment_stays_there() -> None:
    [segment] = transcript_segments(
        [S(0, 5000)], [w(0, 300, " One."), w(3000, 3400, " Two.")]
    )

    assert (segment.start_ms, segment.end_ms, segment.text) == (0, 5000, "One. Two.")


def test_a_word_timed_into_a_pause_goes_to_the_nearest_segment() -> None:
    segments = transcript_segments(
        PHRASES, [w(4600, 4700, " late."), w(4950, 5100, " Early.")]
    )

    assert [s.text for s in segments] == ["late.", "Early.", "", ""]


def test_speech_without_words_keeps_an_empty_segment_and_stops_joins() -> None:
    speech = [S(0, 1000), S(1100, 1400), S(1500, 2500)]
    segments = transcript_segments(
        speech, [w(100, 900, " and so"), w(1600, 2400, " on.")]
    )

    assert [(s.start_ms, s.text) for s in segments] == [
        (0, "and so"),
        (1100, ""),
        (1500, "on."),
    ]


def test_only_silent_speech_at_window_ends_is_decoded_again() -> None:
    speech = [S(0, 1000), S(1500, 2000), S(2500, 3500), S(30000, 31000)]
    windows = speech_windows(speech)
    segments = transcript_segments(speech, [w(1600, 1900, " Hi.")])

    assert unheard_window_ends(windows, segments) == [S(2500, 3500), S(30000, 31000)]


def test_short_bursts_at_window_ends_are_not_decoded_again() -> None:
    speech = [S(0, 1000), S(1500, 1900), S(30000, 30600)]
    windows = speech_windows(speech)
    segments = transcript_segments(speech, [w(100, 900, " Hi.")])

    assert unheard_window_ends(windows, segments) == []


def test_transcript_text_joins_the_segments_with_words() -> None:
    transcript = Transcript(
        "en",
        0.9,
        [
            TranscriptSegment(0, 900, "Hello there."),
            TranscriptSegment(950, 990, ""),
            TranscriptSegment(1000, 1800, "Good morning."),
        ],
    )
    assert transcript.text == "Hello there. Good morning."
