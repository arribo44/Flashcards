// cards/static/cards/flashcards.js

// Typed answers are compared case-insensitively, ignoring punctuation and
// extra spaces. A card may accept several answers separated by , ; or /
function normalize(text, keepAccents = true) {
    let result = text.toLowerCase();
    if (!keepAccents) {
        result = result.normalize("NFD").replace(/[̀-ͯ]/g, "");
    }
    return result.replace(/[.!?¡¿"«»()]/g, "").replace(/\s+/g, " ").trim();
}

function checkAnswer(typed, expected) {
    const candidates = expected.split(/[,;/]/);
    const matches = (keepAccents) => typed.trim() !== "" && candidates.some(
        (candidate) => normalize(candidate, keepAccents) === normalize(typed, keepAccents)
    );
    if (matches(true)) {
        return "correct";
    }
    return matches(false) ? "accents" : "wrong";
}

// Browsers pick a voice from the language alone, often a robotic one (eSpeak on
// Linux): choose the best installed voice instead, or the one the user picked
const PIPER_VOICE = /^[a-z]{2,3}_[A-Z]{2}-[\w-]+-(x_low|low|medium|high)$/;
const GOOD_VOICE = /natural|neural|online|premium|enhanced|google|rhvoice/i;

function baseLanguage(lang) {
    return lang.toLowerCase().split(/[-_]/)[0];
}

function voiceStorageKey(lang) {
    return `flashcards.voice.${baseLanguage(lang)}`;
}

function savedVoiceName(lang) {
    try {
        return window.localStorage.getItem(voiceStorageKey(lang));
    } catch (error) {
        return null;
    }
}

function saveVoiceName(lang, name) {
    try {
        if (name) {
            window.localStorage.setItem(voiceStorageKey(lang), name);
        } else {
            window.localStorage.removeItem(voiceStorageKey(lang));
        }
    } catch (error) {
        // Private browsing or blocked storage: the choice lasts for this page only
    }
}

function voicesFor(lang) {
    return window.speechSynthesis.getVoices()
        .filter((voice) => baseLanguage(voice.lang) === baseLanguage(lang));
}

function voiceScore(voice, lang) {
    const name = `${voice.name} ${voice.voiceURI}`;
    let score = 0;
    if (PIPER_VOICE.test(voice.name)) {
        score += 20;
    }
    if (GOOD_VOICE.test(name)) {
        score += 10;
    }
    if (/espeak/i.test(name)) {
        score -= 10;
    }
    if (voice.lang.toLowerCase().replace("_", "-") === lang.toLowerCase()) {
        score += 1;
    }
    return score;
}

function chooseVoice(lang) {
    const voices = voicesFor(lang);
    const saved = savedVoiceName(lang);
    const chosen = voices.find((voice) => voice.name === saved);
    if (chosen) {
        return chosen;
    }
    return voices.reduce(
        (best, voice) => (best === null || voiceScore(voice, lang) > voiceScore(best, lang) ? voice : best),
        null,
    );
}

function speak(text, lang) {
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = lang;
    utterance.voice = chooseVoice(lang);
    utterance.rate = 0.9;
    window.speechSynthesis.speak(utterance);
}

function fillVoicePicker(picker) {
    const lang = picker.dataset.lang;
    const select = picker.querySelector("select");
    const voices = voicesFor(lang)
        .sort((a, b) => voiceScore(b, lang) - voiceScore(a, lang) || a.name.localeCompare(b.name));
    if (!voices.length) {
        return;
    }
    const best = chooseVoice(lang);
    select.replaceChildren(...voices.map((voice) => new Option(
        `${voice.name} (${voice.lang})`, voice.name, false, best !== null && voice.name === best.name,
    )));
    picker.hidden = false;
}

function setUpVoicePickers() {
    const pickers = document.querySelectorAll(".voice-picker");
    pickers.forEach((picker) => {
        picker.querySelector("select").addEventListener("change", (event) => {
            saveVoiceName(picker.dataset.lang, event.target.value);
            speak(picker.dataset.sample || event.target.value, picker.dataset.lang);
        });
    });
    const refresh = () => pickers.forEach(fillVoicePicker);
    refresh();
    // Voices load asynchronously in most browsers
    window.speechSynthesis.addEventListener("voiceschanged", refresh);
}

function isVisible(element) {
    return element.offsetParent !== null;
}

function setUpSpeech() {
    if (!("speechSynthesis" in window)) {
        return;
    }
    document.querySelectorAll("button[data-speak]").forEach((button) => {
        button.hidden = false;
    });
    setUpVoicePickers();
    document.addEventListener("click", (event) => {
        const button = event.target.closest("button[data-speak]");
        if (button) {
            speak(button.dataset.speak, button.dataset.lang);
        }
    });
}

function setUpTypedAnswer(answer) {
    const form = document.querySelector("form.type-answer");
    if (!form) {
        return;
    }
    const verdict = document.querySelector(".verdict");
    form.hidden = false;
    form.typed.focus();
    form.addEventListener("submit", (event) => {
        event.preventDefault();
        const expected = form.dataset.expected;
        const result = checkAnswer(form.typed.value, expected);
        verdict.textContent = {
            correct: "✅ Correct !",
            accents: `✅ Presque : attention aux accents (« ${expected} »).`,
            wrong: `❌ La réponse attendue était « ${expected} ».`,
        }[result];
        verdict.classList.add(
            { correct: "alert-success", accents: "alert-warning", wrong: "alert-danger" }[result]
        );
        verdict.hidden = false;
        form.typed.disabled = true;
        form.querySelector("[type=submit]").disabled = true;
        answer.open = true;
        // Suggest the matching button: Enter accepts it, the other one stays clickable
        const solved = result !== "wrong";
        answer.querySelector(`form[data-solved="${solved}"] [type=submit]`).focus();
    });
}

function setUpReview() {
    const answer = document.querySelector("details.answer");
    if (!answer) {
        return;
    }
    setUpTypedAnswer(answer);
    document.addEventListener("keydown", (event) => {
        if (event.target.closest("input[type=text], select, textarea")) {
            return;
        }
        // Let Space activate focused links and buttons as usual
        const onControl = event.target.closest("a, button, input, summary");
        if (event.key === " " && !onControl) {
            event.preventDefault();
            answer.open = true;
        } else if (answer.open && ["ArrowRight", "ArrowLeft"].includes(event.key)) {
            event.preventDefault();
            const solved = event.key === "ArrowRight";
            answer.querySelector(`form[data-solved="${solved}"]`).requestSubmit();
        } else if (event.key.toLowerCase() === "p" && !event.ctrlKey && !event.metaKey) {
            const button = [...document.querySelectorAll("button[data-speak]")].find(isVisible);
            if (button) {
                button.click();
            }
        }
    });
}

setUpSpeech();
setUpReview();
