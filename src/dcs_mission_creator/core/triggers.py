"""Voice-plus-text trigger rules — the shape every mission writes twenty times.

A radio call in this project is always the same six statements: make a rule,
attach conditions, post the text on screen, render it as speech, append the rule.
Missions carried roughly twenty hand-written copies of that between them.

The screen text and spoken text normally match. A call may pass `voice_text`
when Piper needs pronunciation-friendly spellings that would look wrong in the
subtitle.

Everything a mission varies stays an argument: the conditions, the comment, how
long the text sits on screen, which coalition hears it. Nothing here decides
when a call happens or what it says.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, Literal

from dcs import action, condition, triggers

if TYPE_CHECKING:
    from dcs.condition import Condition
    from dcs.mission import Mission
    from dcs.triggers import TriggerRule

    from dcs_mission_creator.core.tts import VoiceSynth

Coalition = Literal["blue", "red"]

_COALITION_ACTION = {"blue": action.Coalition.Blue, "red": action.Coalition.Red}


def _attach(
    m: Mission,
    rule: TriggerRule,
    voice: VoiceSynth | None,
    text: str,
    voice_text: str | None = None,
) -> None:
    if voice is not None:
        voice.attach_to_all(m, rule, text if voice_text is None else voice_text)


def message_to_all(
    m: Mission,
    *,
    text: str,
    conditions: Iterable[Condition] = (),
    comment: str,
    voice: VoiceSynth | None = None,
    voice_text: str | None = None,
    seconds: int = 20,
) -> triggers.TriggerOnce:
    """A one-shot call to everyone, spoken and printed, once `conditions` hold.

    This is the end-of-mission shape: success, failure, and the various
    "objective is down" calls. Pass `voice=None` for a text-only rule.
    """
    rule = triggers.TriggerOnce(comment=comment)
    for cond in conditions:
        rule.add_condition(cond)
    rule.add_action(action.MessageToAll(m.string(text), seconds=seconds))
    _attach(m, rule, voice, text, voice_text)
    m.triggerrules.triggers.append(rule)
    return rule


def message_to_coalition(
    m: Mission,
    *,
    text: str,
    conditions: Iterable[Condition] = (),
    comment: str,
    voice: VoiceSynth | None = None,
    voice_text: str | None = None,
    coalition: Coalition = "blue",
    seconds: int = 15,
) -> triggers.TriggerOnce:
    """A one-shot call heard by one coalition only."""
    rule = triggers.TriggerOnce(comment=comment)
    for cond in conditions:
        rule.add_condition(cond)
    rule.add_action(
        action.MessageToCoalition(
            _COALITION_ACTION[coalition], m.string(text), seconds=seconds
        )
    )
    if voice is not None:
        voice.attach_to_coalition(
            m,
            rule,
            text if voice_text is None else voice_text,
            coalition=coalition,
        )
    m.triggerrules.triggers.append(rule)
    return rule


def checkin(
    m: Mission,
    *,
    at_seconds: int,
    text: str,
    comment: str,
    voice: VoiceSynth | None = None,
    voice_text: str | None = None,
    coalition: Coalition = "blue",
    seconds: int = 15,
) -> triggers.TriggerOnce:
    """A support check-in on the clock — tanker on station, TARCAP up, and so on."""
    return message_to_coalition(
        m,
        text=text,
        conditions=(condition.TimeAfter(seconds=at_seconds),),
        comment=comment,
        voice=voice,
        voice_text=voice_text,
        coalition=coalition,
        seconds=seconds,
    )


def intro(
    m: Mission,
    *,
    text: str,
    comment: str,
    voice: VoiceSynth | None = None,
    voice_text: str | None = None,
    coalition: Coalition = "blue",
    seconds: int = 25,
) -> triggers.TriggerStart:
    """The mission-start picture, fired the moment the mission loads.

    A `TriggerStart` rather than a `TriggerOnce`, so it needs its own function
    rather than a condition on `message_to_coalition`.
    """
    rule = triggers.TriggerStart(comment=comment)
    rule.add_action(
        action.MessageToCoalition(
            _COALITION_ACTION[coalition], m.string(text), seconds=seconds
        )
    )
    if voice is not None:
        voice.attach_to_coalition(
            m,
            rule,
            text if voice_text is None else voice_text,
            coalition=coalition,
        )
    m.triggerrules.triggers.append(rule)
    return rule
