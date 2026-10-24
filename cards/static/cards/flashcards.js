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

function speak(text, lang) {
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = lang;
    utterance.rate = 0.9;
    window.speechSynthesis.speak(utterance);
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
