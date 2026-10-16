// Variables used by Scriptable.
// These must be at the very top of the file. Do not edit.
// icon-color: yellow; icon-glyph: tachometer-alt;

/**
 * FORL for iOS, as a Scriptable script.
 *
 * Run it in Scriptable to sign in to Claude and ChatGPT. Add a Scriptable widget
 * to the home screen or the lock screen and pick this script, and the widget
 * shows, unless its Parameter says otherwise:
 *
 *   Home small            the current session, as a dial, the way the Mac small widget does
 *   Home medium           the current session and the week, as bars
 *   Home large            the session and the week of every signed-in service
 *   Lock screen circular  the current session, as a dial
 *   Lock screen rectangular  the current session, its name over its bar
 *   Lock screen inline    the current session, as one line of text
 *
 * A widget's Parameter, set in Edit Widget, lists what it shows instead, as
 * service/usage, such as "claude/session, claude/weekly". The small and lock
 * screen widgets show the first usage listed. The medium widget shows one
 * service, the first one's, up to where the list moves to another. The large
 * widget shows every service listed, each where it first appears. Neither of
 * the last two takes more usages than fit with the same padding all round.
 *
 * The sign-in is the one the desktop apps make: the browser flow of the tool
 * each service built these endpoints for, with a proof key, kept in the iOS
 * Keychain. It runs in Safari, which every account type can sign in with, and
 * the code it ends on is pasted back.
 *
 * The settings also choose the background of the home screen widgets, solid
 * black or solid white, and make the Parameter of a widget from the usages
 * ticked in a list.
 *
 * iOS decides when a widget refreshes, about every quarter of an hour at best,
 * so a widget shows the last reading it was given. Readings that cannot be taken
 * leave the last good one on screen.
 */

// Services --------------------------------------------------------------------

const CLAUDE = "claude";
const CHATGPT = "chatgpt";

/** Everything that differs between the two services. */
const SERVICES = {
	[CLAUDE]: {
		key: CLAUDE,
		label: "Claude",
		authorizeURL: "https://claude.com/cai/oauth/authorize",
		tokenURL: "https://api.anthropic.com/v1/oauth/token",
		clientId: "9d1c250a-e61b-44d9-88ed-5944d1962f5e",
		scope: "user:profile user:inference",
		// The hosted page that shows the code to paste back.
		redirectURI: "https://platform.claude.com/oauth/code/callback",
		authorizeExtras: { code: "true" },
		headers: { "User-Agent": "claude-usage-widget/1.0" },
	},
	[CHATGPT]: {
		key: CHATGPT,
		label: "ChatGPT",
		authorizeURL: "https://auth.openai.com/oauth/authorize",
		tokenURL: "https://auth.openai.com/oauth/token",
		clientId: "app_EMoamEEZ73f0CkXaXp7hrann",
		scope: "openid email offline_access",
		// The one redirect this client is allowed. Nothing listens on it, so the
		// sign-in ends on a page that does not load, whose address is pasted back.
		redirectURI: "http://localhost:1455/auth/callback",
		authorizeExtras: { id_token_add_organizations: "true", codex_cli_simplified_flow: "true" },
		headers: { "User-Agent": "chatgpt-usage-widget/1.0", originator: "codex_cli_rs" },
	},
};
const SERVICE_KEYS = [CLAUDE, CHATGPT];

const SESSION = "session";
const WEEKLY = "weekly";
const PRODUCT_PREFIX = "product:";

// Widget sizes ----------------------------------------------------------------

const SIZES = {
	small: { single: true },
	medium: { single: false },
	large: { single: false },
	accessoryCircular: { single: true },
	accessoryRectangular: { single: false },
	accessoryInline: { single: false },
};

// How long a widget waits before asking iOS for a new reading, in minutes.
const REFRESH_MINUTES = 15;
// How long before a token runs out it is renewed, in milliseconds.
const RENEW_MARGIN_MS = 5 * 60 * 1000;

// Where things are kept. Sign-ins in the Keychain; the widget background and
// the last reading of each service in the script's own documents folder.
const KEYCHAIN_PREFIX = "io.forl.tokens.";
const files = FileManager.local();
const CACHE_PATH = files.joinPath(files.documentsDirectory(), "forl-readings.json");
const SETTINGS_PATH = files.joinPath(files.documentsDirectory(), "forl-settings.json");

// Look ------------------------------------------------------------------------

// The stops of the usage ramp, from green to red, as on the Mac and the desktop.
const USAGE_RAMP = [[0, [48, 209, 88]], [50, [227, 193, 59]], [75, [232, 145, 45]], [100, [255, 69, 58]]];
const TRACK_OPACITY = 0.22;
// The dial of the small widget, as shares of its square, from the Mac's
// DialGeometry. The lock screen dial is drawn thicker and larger, because it
// is seen smaller and in one tone.
const DIAL = { radius: 0.40, stroke: 0.065, start: 135, sweep: 270, markSize: 0.20, markCenterY: 0.82, number: 0.30 };
const LOCK_DIAL = { radius: 0.42, stroke: 0.10, start: 135, sweep: 270, markSize: 0.24, markCenterY: 0.84, number: 0.36 };

// The two backgrounds a home screen widget can have, chosen in the settings.
const BACKGROUNDS = ["black", "white"];
const DEFAULT_BACKGROUND = "black";

// The service marks, rendered from src/common/assets by the desktop widget's
// own renderer: Claude in its orange, ChatGPT in white for a black background
// and in black for a white one.
const MARKS = {
	claude: "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",
	chatgptWhite: "iVBORw0KGgoAAAANSUhEUgAAAGAAAABgCAYAAADimHc4AAASp0lEQVR42u1da9CdVXV+1jnn+yJqGhIL6RCmtpQmIpQpYglMRhOMIQ2WTkf/BLTjNJI67TQ2HesPLZoIOm1BW0fHSoN8wFQHtepMHeWSi8SOnZJAiEZikgqDAWG4SBLAEfKdc96nP87aZLHYe7/vec/l+3R4Z86c23tda+1nrb1uWzADG8kGABGRrn5vAngjgEsB/C6APwJwLoCWO7QN4H4APwHwNQDbReQZc94WgK6IEK9sUcKLEjt8X0LyYyT3kXye/W8PkfwiyctIzjHnbb5C7bjUh88XkvwWyeOOoB19dTNE7+qrcL8fJLmZ5MJwPZLyCuWNRJKcR/KzJKcd0T1BC/0tMKRtPheOGW3HsCdIbkiNBmVMk2Qr8fr1YpziMkguI3nIEb4wBI8ROLV1IoQPzAjbV0nO12tPKNGlH6FRhjRHyRAZJd4DaIhIl+R6AP+mSrUDoKnXJoBCv9vtGIDnADwA4GkADwM4D0ADwEUAJs2+Xf09PAv1txaAvQDeJyJ7zX29EcBCAK8H8Du6f9gOA9gF4LCI/DIyiothK3gZIfFFRAqS/wpgoyO2J/yTAP4LwNeV+D8BcNwTQc/9BgC/DeDtAK4AsCjBiI4y4SiAvwfwBwCWAXhThOFwDH0MwL0A9gC4C8AuZ7EVs9bSUkunoZ+3RODGwsbjJDcFxRlT3AYKGlaR6/9zSV5F8pGMwk79HmDMvjqJ/fdbBe+NilmncJUJgfjThvjhAdskr3YP1DQvSeGuZYr5bT7Ja0keTih0q8jLdEzhGFQ4gbmK5ITVb7PR2tlkiE9H/PtILrVKuq6SU0ZMmO9T7lop5d021lc3MiK6CWsrbHeHZ5g1VpOBnfOV8O2I5O82lskghPcTustJHjASzMgIKGpM9NqR0dQ2/20aFJJkmAxQpbsTwHJVZk1Vtg0ATwE4W0SeItkSkU5dszYcS/IcANcCWKN/h2shYWHdA2A/gAcB7FbXRrDG5qv74/UAlgJYbI71Ct5+nwKwUUSeCzSYSehZ4SQ+4OnPSV4wiJvA2uMkTyV5jZlJd53C7UQU/QV9Xutcktfp8bHzFgZid6keasyIcjbwc5e70UCUS+oqrQjcrCP5aIIolhHHlUmn+nOZCZZ/tSIz54UkrzTXbDuYCkLw9UGhdVjS33WEuasO8SOEX0lyewKfC8eIWxWerKJv9GtKO0vrNJ1dM6KkA1OuH7sz0DDgVnczQRpX9HtTjvCnGesm5sKwEvkjkmuGYWE5ZlhGbHQw5Jnw/rExwWDyb5I8GpHGe/qxECyGkpwkuUGdazEp73gHHMlJf55hwqy5t9Wq14rIKOyqm11Gqg/0ApOKncuMwrXEeW8VaYhI2RqVZkZwt+tMwSmSi8YVCzCTsLdnhOLOkc2WPTbrb++JwMNTJH/DjpQKcLPEQFkZ3Gx3E7pKXsuIK7pRgwZhpG2OCEhgwoqhC4Qj1kK1SKZIPmyGY7iB75dBgRnS89RUPFbBrDxEcl0NwkuKGDVc1cGamtCZfdT4GBoUOvxbRPIGZx8zQqxv5CTA6I/VkThBzqyc1w/OR+BtqfpzPk3yb0meUQe+jPFxHskXnGUU7nnpwKPASb1Vikw4rMJw/HjK/DTMfLM5tu0eIGtWDsGaCtsxZUjfCtww4eaIs5EkrxvIaWcusJjkHRkfSWwEbMwwIETJvuAmM960q2VWRqypq5w1ZV3Qta8VHHEkz3Je366By4laprDR9utIPpMgfDcyMwwXf2tq+LmZc+FcFyT5oI62OQPCTc6aYmYSt7gqLBkmfD/iBeiSXNY3DBkCrc9gc6ckCPK2CgzYEQnM/x/J1/WLyw5uzslYU7mYcrdfWDKj+ROOyeH9H3Iw1Eg8CNXVukU9itarGDyOTQAHAfyzhv3g4qvs0xtL/f6QiDwdhm4IBZbBjcae55G8RkOJa929i/ve0ufo6rUb5vs8ANcA2ENyjYgU6umNwVJ4zj0JD/MplelhuLkpATltawqa/Y847ydJXlxhBHzX5QMF8610FhnxFa3NWFN+DrGV5Mc11FjVt7Q4MdqaJuujGzFHv1dpUubMqmmnVCy07HYQccqQGfDdshuOmJVbMwaCV7Rr7YTKKeicGRyFJecifzbCwG2lDDATi7kkfxgJaHeMJCwwNy/qBx8LAyIxAZvkFZu85YhnmbhITdTpChNBby1NKB1eqzFpf/xh/S8Z57bS//mI1ISbutprfhMQHykD+owJ+G0qAx/Sx2hKwpJJFNgRUfrPBcSIMsAQf3nC8UWS/2uCGA03kx0ZAyrEBDqJGPALJG8nubqKXZ/QJzlnoB9Zr9LjtkeeZ1fW5xSISnJnxI4tSP6A5AKvGMfAgImKMQFP/EKV8cJY5kSNCdyxhOndcXlDl2mWt993exUdcH4E9/2EqpXw5cwfgRVUNSYQm48Exjyp1lxtF4PxAkwldEtRkgJT7ppWyb7RHeTDic2MM23YDAg3fCnJ+xMwUGSslTJ3Rj/e01bFkGg3koUX7vfarD+I5OscAS38XDxGBoTj7iF5U0kWddj29qE0b6vp0GtEDIBDJe4NK8RX+Ew+f4E/TrhS95cpriEzIJUimApB2hTBmNIsyjIlcjGClK408YvNRj8UEZ0U7vfPvU7zJ746AT/rc5IyQgbEwnyWgJ91qSaNipMq+/nROkGdRARvKgOThcaOVyf1AMltDnYKkr8keWZOeYxhBHQrpJpIhCi5SVUsrLmyhrvb64cQpGdGF62K0oPkvZFcl6MkT87Fc8c4AraHm89J64CTqimSp9XwwDaMP2xxJDXH6rDHbf2aPckzEeLdWxZIGMMI+JGDiX5iArlJFRMK/olBI2P6+YOZQP1Wr9SRUBy3V3CIDZsBAf6OOEJInZhqYlJ1JKEw20MwW+1o2BIRrHCNj7yELgnP4SfLTLURzgO2DUL4EgfethKrayCz1VUHbUskKj+tiWxCUhqJFPXnMXNbSJBtlAVjqmx6jjDsY0QMRX1i0ukL9FLe9wSzVUQ6ZUIR6saU4e8B8LgJBIX3BQA26L7NFMQsmEEGUInGMZ1TXOGgjYxNArgKwF6S60SEGnlLwpLWBzRF5AkAH9ZzheuG6/wVyVcD6DbQqyb0Icrloe/CENLWZ2cxW4/YQK8a8mZlhA1RBmJ1AJwG4MZgtopIWT+Krj77rQAO6XntKDgFwLtEhA30KkZgdgCAMwEsEBHWSKkID3aZxlLboy52risf+n5ERP4CwGr0aoRD/DgIX8vA1EoA23UyOCcVZFHmiIgcB/CPpgrHxow/RHKyYYLJNBx6LYDfTwXuMw9jb3gDyW+QPDtIzCxtojGpQf2tAN4C4APo1S1bRgSY6uprA4AvuLKllwmijoKvqJA3XQnVYgBnNpTrljNhpwsq1pHR3JzF1RaAdwK4T/0mk4qfjVFW6NfUDwXJCRFpi8jn0Cvq/hyAaVdj1jQw9W5FiSIzCho6Cr7q0KEAMAfAHzYA/MBIv5X49+X0gJHoZ9Crcm8qXhau6nwSwCaX4tGdhaOhG6wcEXlSRD4A4HwA39RnshASRsRZJSgRIPx/IgWEAPDmBoB9+rLSXwA4G8BbSqAjEPuDAG4HMKHHd5wi6wI4B8BtOl0/fQSWDoZgsgYrJzDifhF5F4BPOr0Ak1uU1Yc6Evah1/ui4YR9WUNEXgBwi8F/y6GPVbhhisjPReRSAJej19GqpefrROzrtQpL62cZFMUYMaGQeUcCjll2Hh0BxwA8ZI5pvDgCdIcvoVfH2zSSWwBYQXJ5GWSEGaCIfEWH7UdVkVkLwtrXp6CXdfdWI02z0lRVu/6kAc7R0Lrm+xxqAECjAaAlIk8B+I/IMAOATyvxJTP5CIqsKSLTIvIJ9NrL3OQsiFS3lJecLlxvmEI94DmLIXSkeSCVG9pVwt6IXuV4wwyTrkr0p5SLrbJpf3ALi8hjIrIOvbYyO4wF0SlRXB3VD8WwfEEqyV036Rz3fOO3+mmyEXOlru/TVy4lsdROIgR5ZBgVj84b2tJzHjFxj0qZePp+sQu2lDocI47H/449d6zNzNaEF+8lNbD9+MpdLDXXYoAjyGZYpd1NUkHzcTFga8xFHSs0WKjRmyKR/3J9nUJoR5RzSqohs27hTJTO5/OU1QiMgwGibov9EaHbl7rgqkRJfsc0xKsTwiuTzk4mm8EH45t9ZLR1Z2IEmHs6XePsHlHuyOmD9Ym2X51Bq9MdwSYSxX+xzz9TXTKRyHL2JUk+easYMwMCrP9ZIvPkn6oWanQSTKiN1REpDunmxxPZDB3XsWqVg7TbKhZ4j5UB+v6tRBeZK8oSdt+RaX7nibK1TiuyiLXkiZnLZrhZhaRqXv+DkfOMhAFGpy5R+ClcPPpZ22IhNQKuTqTfpbB6Ota7oSYjfDZDkYGTssqWzSRfYxjbGQMDwrG3JODni1WqJL9ZoQleKnVwc6hqr5FrYxXqJs10ZoLoZfk+S8y5d46DAQZBlrtr2WPP77cDVmEk6l+0CKIMqw9GlGZVRT1hCLBQJ3FFpi7AdzVc6WrBpE5JVE0GtBIdxML7zpflB8VyXLS6w+dnHtB9zuqjs8ndVbLbMml/tyvDi5JR6K2klhtRI2eAufb7MyiRVt4mh2aBy5p7MWnLEq9Cb59cfmfTnStXGJFqY5/qD9ccRlFgVQao4ExETPii74INfT/ZYe+LI4Dkq0Oju0w/hm6GWH5S1eqjNKjvmfIYGDBp6LY+0675QU3Kyjd7NSbUzoQOmJewXMpquWJtxiYqFscVdVMIR8iAlWaflmng1I3A8TTJC6sWbcc8eDZ1/Sy3X6yc5+6Kvp7dJP+O5NcyxdYD9YczAnXXkBlwEU60L7s7YSKHOcqmypU5kT44bc/5hPYXYwFMqEL8WaZ9QCeD65XmGH12ftk6JAYEiF1vaqtj86VA/C1eSKv2jPhIogPIX+dO2IeLwba8KevtsHTAjGUx/aWtXtlRgwFMLLkSu/8tfTf5zjSgCCf9UkU3bKuii4GZ/nBrh1ThuMMRrrSZRgkDUlJvv19fpyedfYgJE8WyJUzPV+2NWaGrSTsyoz1mZ9IDFEv4Gq4iIgBfruBOeFvJghB+ZD8aBKd2e3szdK9znA2Sc8sALoZQZXi0n94OA1QxxqrcAzOWV2DA8gQExVZxujXESgbqmGgufmEkOtbVmenifi/kJPQMkh8i+W0l2NKa/eGqxp49nK4vKUQMQvg3JTXB1DYFa/qtQ67aHffHic642+pUspQp8Jr94cqae0eVekkZVhDCmxwDCjUq9ut/l5h9h7eihjnpezM1T5uzhcgVrJRU6/iaON/JlKX6hk2VWio7PRho8OGYF3QkKyJpUPlgJuCxsi4TatR79YPzrFsB6SygrpuEFWYSNjnS+gdzI5cknG0FyQeMPhj6zQyA84NM3nIu+aO20G6cawT8e8JHE0zHK4c5HIeF8zVSaHKLUhQkvz3WtcQMFAl73bNSnbXIXl/peXUbYycIPxDO17h+sySg8iczsVJG6BK4QB1ouR4+hzRO0MysYtq0bcliilgjYZtGhfMlxF8eccAVqgtPGhv8JHBxvmHCdMaV8EN1WJ3a53UC4R8fJc5nhExI7nGmd7ufRSkwqnXEzHph8wHcid7y422cKMoATlRchu9PAPgxgJ+itzLqYf38GHqVI0vQq665AL3FNpcBONUsytmM1LABwDYAHxWRXYMuaa6p9WHBzhsAXGnWQgvve9FbzbWttWWc6VXzFriu6p2SljMxR9YvKjTS8Ar/AMnLB8H5hAt9Ll/evs0GVM6bNQt5ug6KGwxOp5YAjK3j6CElt+BmIMhULHNiCGsjLOWJ1TDaAwVUZmjp2iXqbvZKMrdGfCzNxC6sGasf+Kn6Zl7lTMxmhX7/diE3McduijgbLSO2DKt5yEjnCfo5LAH4SMkyse3I56ICg2yqy59SFwrKLNLTSvmXItnZ3RjxZ9WqqWVxV7fY8jqSd/JET+Uq28Mk/5PkZyqGMh9Rhl9UwbczVydz1xkrLhaznnbEH5mrQUakGxp2tVSSJ6FXff4anFjLvaUWz31qVRxGr6R/f1jKXDtmfQbAXLNEOVzhnJXsA+itabDP3da5AE5Gr/3C6a5+y5aN2lVSbxCRv5z1S5hXwNtakyETSH+TyzhIrfFbdb3gWAy64+z9jb8SsFODGc0INvvvEpmV2pwbi9HdPtaK70QiWv63rbNupexZZu5eqPh9LDIC2i5/iS4nv+NedIRfNa7lEH9lR5Bzzn1KI3XMmLhlULQtrHU8qkVAx66ExzAaGmZJ86a6L1YAOAPA7wF4A3ot1+YAeBa9ljNdVfBd9Po2fAfAbhE5YM4rw+hR92vNgJylZf47GcAifR0E8Au1Yo4lEpEbM0H4sP0/SVMKrtvNzqcAAAAASUVORK5CYII=",
	chatgptBlack: "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",
};

// Validation ------------------------------------------------------------------

/**
 * Throw a TypeError unless a value has the expected type.
 *
 * @param {*} value The argument to check.
 * @param {string} type What typeof must report, or "array".
 * @param {string} name The argument's name, used in the message.
 * @returns {void}
 */
function requireType(value, type, name) {
	const actual = Array.isArray(value) ? "array" : typeof value;
	if (actual !== type) {
		throw new TypeError(`${name} must be ${type}, got ${actual}`);
	}
}

/**
 * Throw a RangeError unless a value is one of the allowed ones.
 *
 * @param {*} value The argument to check.
 * @param {Array} allowed The values accepted.
 * @param {string} name The argument's name, used in the message.
 * @returns {void}
 */
function requireMember(value, allowed, name) {
	requireType(allowed, "array", "allowed");
	if (!allowed.includes(value)) {
		throw new RangeError(`${name} must be one of ${allowed.join(", ")}, got ${value}`);
	}
}

// Storage ---------------------------------------------------------------------

/**
 * Return a JSON document kept in the documents folder, or a fallback.
 *
 * @param {string} path The file. A missing or broken one gives the fallback.
 * @param {object} fallback What to return when there is nothing usable.
 * @returns {object} The decoded document.
 */
function readJSON(path, fallback) {
	requireType(path, "string", "path");
	try {
		if (files.fileExists(path)) {
			const value = JSON.parse(files.readString(path));
			if (value && typeof value === "object") {
				return value;
			}
		}
	} catch (error) {
		// A file that cannot be read costs the choice it held, not the script.
	}
	return fallback;
}

/**
 * Write a JSON document to the documents folder.
 *
 * @param {string} path The file to replace.
 * @param {object} value The whole document.
 * @returns {void}
 */
function writeJSON(path, value) {
	requireType(path, "string", "path");
	requireType(value, "object", "value");
	files.writeString(path, JSON.stringify(value));
}

/**
 * Return a service's stored sign-in.
 *
 * @param {string} service CLAUDE or CHATGPT.
 * @returns {object|null} The tokens, or null when nobody is signed in.
 */
function loadTokens(service) {
	requireMember(service, SERVICE_KEYS, "service");
	const key = KEYCHAIN_PREFIX + service;
	if (!Keychain.contains(key)) {
		return null;
	}
	try {
		return JSON.parse(Keychain.get(key));
	} catch (error) {
		return null;
	}
}

/**
 * Keep a service's sign-in, or forget it.
 *
 * @param {string} service CLAUDE or CHATGPT.
 * @param {object|null} tokens The tokens, or null to sign out.
 * @returns {void}
 */
function saveTokens(service, tokens) {
	requireMember(service, SERVICE_KEYS, "service");
	const key = KEYCHAIN_PREFIX + service;
	if (tokens === null) {
		if (Keychain.contains(key)) {
			Keychain.remove(key);
		}
		return;
	}
	requireType(tokens, "object", "tokens");
	Keychain.set(key, JSON.stringify(tokens));
}

// Sign-in ---------------------------------------------------------------------

/**
 * Return a proof key verifier, its challenge, and a state, made with WebCrypto.
 *
 * JavaScriptCore, which runs this script, has no cryptography, so the values
 * are made inside a web view, whose engine has a secure random source and
 * SHA-256.
 *
 * @returns {Promise<{verifier: string, challenge: string, state: string}>} The values, base64url.
 */
async function proofKey() {
	const view = new WebView();
	// The work runs inside a function and the script ends on a plain value:
	// WebKit hands back strings and numbers but not the Promise the digest
	// returns, and refuses the whole evaluation when the script ends on one.
	// The result itself comes back through completion().
	const script = `
		(() => {
			const encode = bytes => btoa(String.fromCharCode(...new Uint8Array(bytes))).replace(/\\+/g, "-").replace(/\\//g, "_").replace(/=+$/, "");
			const random = length => encode(crypto.getRandomValues(new Uint8Array(length)));
			const verifier = random(32);
			crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier))
				.then(digest => completion(JSON.stringify({ verifier, challenge: encode(digest), state: random(32) })))
				.catch(error => completion(JSON.stringify({ error: String(error) })));
		})();
		0;
	`;
	await view.loadHTML("<html><body></body></html>", "https://localhost/");
	const result = JSON.parse(await view.evaluateJavaScript(script, true));
	if (result.error) {
		throw new Error(`Could not prepare the sign-in: ${result.error}`);
	}
	return result;
}

/**
 * Return the page a sign-in starts at.
 *
 * @param {object} service The service, from SERVICES.
 * @param {string} redirectURI Where the page sends the code.
 * @param {{challenge: string, state: string}} key The proof key and state.
 * @returns {string} The full address.
 */
function authorizationURL(service, redirectURI, key) {
	requireType(service, "object", "service");
	requireType(redirectURI, "string", "redirectURI");
	const fields = Object.assign({}, service.authorizeExtras, {
		client_id: service.clientId,
		response_type: "code",
		redirect_uri: redirectURI,
		scope: service.scope,
		code_challenge: key.challenge,
		code_challenge_method: "S256",
		state: key.state,
	});
	const query = Object.entries(fields).map(([name, value]) => `${encodeURIComponent(name)}=${encodeURIComponent(value)}`).join("&");
	return `${service.authorizeURL}?${query}`;
}

/**
 * Return the parameters of an address's query string.
 *
 * @param {string} address The address.
 * @returns {object} Each parameter by name.
 */
function queryOf(address) {
	requireType(address, "string", "address");
	const result = {};
	const query = address.split("#")[0].split("?")[1] || "";
	for (const pair of query.split("&")) {
		if (!pair) {
			continue;
		}
		const [name, value = ""] = pair.split("=");
		result[decodeURIComponent(name)] = decodeURIComponent(value.replace(/\+/g, " "));
	}
	return result;
}

/**
 * Post a form to a token endpoint and return its answer.
 *
 * @param {object} service The service, from SERVICES.
 * @param {object} fields The form fields.
 * @returns {Promise<object>} The decoded answer.
 */
async function tokenRequest(service, fields) {
	requireType(service, "object", "service");
	requireType(fields, "object", "fields");
	const request = new Request(service.tokenURL);
	request.method = "POST";
	request.headers = Object.assign({ "Content-Type": "application/x-www-form-urlencoded", Accept: "application/json" }, service.headers);
	request.body = Object.entries(fields).map(([name, value]) => `${encodeURIComponent(name)}=${encodeURIComponent(value)}`).join("&");
	const text = await request.loadString();
	const status = request.response ? request.response.statusCode : 0;
	if (status < 200 || status >= 300) {
		throw new Error(`${service.label} refused the sign-in (HTTP ${status}).`);
	}
	return JSON.parse(text);
}

/**
 * Return the claims of a JSON web token, without checking its signature.
 *
 * @param {string} token The token.
 * @returns {object} The claims, empty when the token cannot be read.
 */
function claimsOf(token) {
	requireType(token, "string", "token");
	try {
		let part = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
		while (part.length % 4) {
			part += "=";
		}
		return JSON.parse(Data.fromBase64String(part).toRawString());
	} catch (error) {
		return {};
	}
}

/**
 * Return the tokens to keep from a token endpoint's answer.
 *
 * @param {object} service The service, from SERVICES.
 * @param {object} answer The token endpoint's answer.
 * @param {object|null} previous The tokens this answer renews, if any.
 * @returns {object} The tokens, with who they belong to.
 */
function tokensFrom(service, answer, previous) {
	requireType(service, "object", "service");
	requireType(answer, "object", "answer");
	if (typeof answer.access_token !== "string" || !answer.access_token) {
		throw new Error(`${service.label} sent no sign-in.`);
	}
	const tokens = Object.assign({}, previous || {}, {
		access: answer.access_token,
		refresh: answer.refresh_token || (previous ? previous.refresh : ""),
		expires: Date.now() + (Number(answer.expires_in) || 3600) * 1000,
	});
	if (typeof answer.id_token === "string") {
		const claims = claimsOf(answer.id_token);
		const auth = claims["https://api.openai.com/auth"] || {};
		tokens.accountId = auth.chatgpt_account_id || tokens.accountId || "";
		tokens.account = claims.email || claims.name || tokens.account || "";
	}
	return tokens;
}

/**
 * Sign in to a service in Safari, and take the code back from the user.
 *
 * Safari rather than a browser inside Scriptable, because Google refuses to
 * sign in inside apps. Claude shows the code on a page of its own; ChatGPT ends
 * on an address that does not load, which the user copies from the address bar.
 *
 * @param {string} serviceKey CLAUDE or CHATGPT.
 * @returns {Promise<boolean>} Whether the sign-in completed.
 */
async function signInInSafari(serviceKey) {
	requireMember(serviceKey, SERVICE_KEYS, "serviceKey");
	const service = SERVICES[serviceKey];
	const key = await proofKey();
	const redirectURI = service.redirectURI;
	Safari.open(authorizationURL(service, redirectURI, key));
	const prompt = new Alert();
	prompt.title = `Sign in to ${service.label}`;
	prompt.message = serviceKey === CLAUDE
		? "Sign in in Safari, copy the code it shows, then paste it here."
		: "Sign in in Safari. It ends on a page that does not load: copy its whole address and paste it here.";
	prompt.addTextField("Paste here");
	prompt.addAction("Sign in");
	prompt.addCancelAction("Cancel");
	if ((await prompt.presentAlert()) === -1) {
		return false;
	}
	const pasted = prompt.textFieldValue(0).trim();
	let code = "";
	let state = "";
	if (pasted.includes("code=")) {
		const query = queryOf(pasted);
		code = query.code || "";
		state = query.state || "";
	} else {
		[code, state = ""] = pasted.split("#");
	}
	if (!code || state !== key.state) {
		throw new Error("That is not the code of this sign-in. Try again.");
	}
	await finishSignIn(serviceKey, code, redirectURI, key);
	return true;
}

/**
 * Exchange a sign-in's code for tokens and keep them.
 *
 * @param {string} serviceKey CLAUDE or CHATGPT.
 * @param {string} code The code the sign-in ended with.
 * @param {string} redirectURI The redirect the sign-in named.
 * @param {{verifier: string, state: string}} key The proof key and state.
 * @returns {Promise<void>}
 */
async function finishSignIn(serviceKey, code, redirectURI, key) {
	requireMember(serviceKey, SERVICE_KEYS, "serviceKey");
	requireType(code, "string", "code");
	const service = SERVICES[serviceKey];
	const answer = await tokenRequest(service, {
		grant_type: "authorization_code",
		code,
		client_id: service.clientId,
		redirect_uri: redirectURI,
		code_verifier: key.verifier,
		state: key.state,
	});
	const tokens = tokensFrom(service, answer, null);
	if (serviceKey === CLAUDE) {
		tokens.account = await claudeAccount(tokens.access);
	}
	saveTokens(serviceKey, tokens);
}

/**
 * Return a service's access token, renewing it when it is about to run out.
 *
 * @param {string} serviceKey CLAUDE or CHATGPT.
 * @returns {Promise<object|null>} The tokens, or null when nobody is signed in.
 */
async function usableTokens(serviceKey) {
	requireMember(serviceKey, SERVICE_KEYS, "serviceKey");
	const tokens = loadTokens(serviceKey);
	if (!tokens || tokens.expires - Date.now() > RENEW_MARGIN_MS || !tokens.refresh) {
		return tokens;
	}
	const service = SERVICES[serviceKey];
	const answer = await tokenRequest(service, {
		grant_type: "refresh_token",
		refresh_token: tokens.refresh,
		client_id: service.clientId,
		scope: service.scope,
	});
	// Both services retire a refresh token once it is used, so the new one is
	// kept before anything else can fail.
	const renewed = tokensFrom(service, answer, tokens);
	saveTokens(serviceKey, renewed);
	return renewed;
}

// Readings --------------------------------------------------------------------

/**
 * Return a JSON document from an endpoint.
 *
 * @param {string} url The endpoint.
 * @param {object} headers The request headers.
 * @returns {Promise<{status: number, body: object|null}>} The status and the decoded body.
 */
async function getJSON(url, headers) {
	requireType(url, "string", "url");
	requireType(headers, "object", "headers");
	const request = new Request(url);
	request.headers = headers;
	let body = null;
	try {
		body = JSON.parse(await request.loadString());
	} catch (error) {
		body = null;
	}
	return { status: request.response ? request.response.statusCode : 0, body };
}

/**
 * Return the headers every Claude request carries.
 *
 * @param {string} access The access token.
 * @returns {object} The headers.
 */
function claudeHeaders(access) {
	requireType(access, "string", "access");
	return Object.assign({ Authorization: `Bearer ${access}`, "anthropic-beta": "oauth-2025-04-20", Accept: "application/json" }, SERVICES[CLAUDE].headers);
}

/**
 * Return who is signed in to Claude.
 *
 * @param {string} access The access token.
 * @returns {Promise<string>} The email address, or an empty string.
 */
async function claudeAccount(access) {
	requireType(access, "string", "access");
	const answer = await getJSON("https://api.anthropic.com/api/oauth/profile", claudeHeaders(access));
	const account = (answer.body && answer.body.account) || {};
	return account.email || account.display_name || "";
}

/**
 * Return a share, clamped to 0 to 100.
 *
 * @param {*} value What the endpoint reported.
 * @returns {number} The share.
 */
function clampPercent(value) {
	const number = Number(value);
	return Number.isFinite(number) ? Math.min(100, Math.max(0, number)) : 0;
}

/**
 * Take one Claude reading.
 *
 * @param {object} tokens The sign-in.
 * @returns {Promise<Array<{key: string, label: string, percent: number}>>} Every usage, in panel order.
 */
async function readClaude(tokens) {
	requireType(tokens, "object", "tokens");
	const answer = await getJSON("https://api.anthropic.com/api/oauth/usage", claudeHeaders(tokens.access));
	if (answer.status === 401 || answer.status === 403) {
		throw new Error("Sign-in expired");
	}
	if (!answer.body) {
		throw new Error(`Claude answered HTTP ${answer.status}`);
	}
	const document = answer.body;
	const usages = [];
	const scoped = [];
	let session = null;
	let weekly = null;
	for (const entry of Array.isArray(document.limits) ? document.limits : []) {
		if (!entry || typeof entry !== "object") {
			continue;
		}
		if (entry.kind === "session" && !session) {
			session = { key: SESSION, label: "Current session", percent: clampPercent(entry.percent) };
		} else if (entry.kind === "weekly_all" && !weekly) {
			weekly = { key: WEEKLY, label: "This week", percent: clampPercent(entry.percent) };
		} else if (entry.kind === "weekly_scoped") {
			const scope = entry.scope || {};
			const holder = scope.model || scope.surface || {};
			const name = holder.display_name || "";
			scoped.push({ key: `scoped_${scoped.length}`, label: name ? `${name} this week` : `Scoped limit ${scoped.length + 1} this week`, percent: clampPercent(entry.percent) });
		}
	}
	if (!session && document.five_hour) {
		session = { key: SESSION, label: "Current session", percent: clampPercent(document.five_hour.utilization) };
	}
	if (!weekly && document.seven_day) {
		weekly = { key: WEEKLY, label: "This week", percent: clampPercent(document.seven_day.utilization) };
	}
	usages.push(session || { key: SESSION, label: "Current session", percent: 0 });
	if (weekly) {
		usages.push(weekly);
	}
	usages.push(...scoped);
	const breakdown = document.seven_day_breakdown || {};
	for (const row of Array.isArray(breakdown.rows) ? breakdown.rows : []) {
		const name = row && (row.display_name || row.key);
		if (name) {
			usages.push({ key: PRODUCT_PREFIX + (row.key || name), label: name, percent: clampPercent(row.percent) });
		}
	}
	return usages;
}

/**
 * Wait a while.
 *
 * @param {number} milliseconds How long.
 * @returns {Promise<void>}
 */
function pause(milliseconds) {
	requireType(milliseconds, "number", "milliseconds");
	return new Promise(resolve => Timer.schedule(milliseconds, false, resolve));
}

/**
 * Take one ChatGPT reading.
 *
 * The endpoint refuses a token it has only just issued for a few seconds, and
 * the odd request for no reason it gives, so a refusal is tried again before
 * it is believed.
 *
 * @param {object} tokens The sign-in.
 * @returns {Promise<Array<{key: string, label: string, percent: number}>>} Every usage, in panel order.
 */
async function readChatGPT(tokens) {
	requireType(tokens, "object", "tokens");
	const headers = Object.assign({ Authorization: `Bearer ${tokens.access}`, Accept: "application/json" }, SERVICES[CHATGPT].headers);
	if (tokens.accountId) {
		headers["chatgpt-account-id"] = tokens.accountId;
	}
	let answer = null;
	for (let attempt = 0; attempt < 3; attempt++) {
		if (attempt) {
			await pause(1000);
		}
		answer = await getJSON("https://chatgpt.com/backend-api/codex/usage", headers);
		if (answer.body && answer.status >= 200 && answer.status < 300) {
			break;
		}
	}
	if (!answer.body || answer.status < 200 || answer.status >= 300) {
		throw new Error(answer.status === 401 ? "Sign-in expired" : `ChatGPT answered HTTP ${answer.status}`);
	}
	const limits = answer.body.rate_limit || {};
	const usages = [{ key: SESSION, label: "Current session", percent: clampPercent((limits.primary_window || {}).used_percent) }];
	if (limits.secondary_window) {
		usages.push({ key: WEEKLY, label: "This week", percent: clampPercent(limits.secondary_window.used_percent) });
	}
	return usages;
}

/**
 * Return a reading of every service someone is signed in to, keeping the last good one.
 *
 * @returns {Promise<object>} By service key: { usages, signedIn, error }.
 */
async function readAll() {
	const cache = readJSON(CACHE_PATH, {});
	const result = {};
	for (const key of SERVICE_KEYS) {
		const reading = { usages: (cache[key] && cache[key].usages) || [], signedIn: false, error: "" };
		try {
			const tokens = await usableTokens(key);
			if (tokens) {
				reading.signedIn = true;
				reading.usages = key === CLAUDE ? await readClaude(tokens) : await readChatGPT(tokens);
				cache[key] = { usages: reading.usages, at: Date.now() };
			} else {
				reading.usages = [];
				delete cache[key];
			}
		} catch (error) {
			// The last good reading stays on screen; only the reason is new.
			reading.error = String(error.message || error);
		}
		result[key] = reading;
	}
	writeJSON(CACHE_PATH, cache);
	return result;
}

// Choices ---------------------------------------------------------------------

// How the medium and large widgets are laid out, in points: the padding on
// every side, a service's heading and the space under it, a row and the space
// between rows, and the space between two services.
const LAYOUT = { padding: 16, heading: 16, headingGap: 8, row: 16, rowGap: 6, sectionGap: 28 };
// The heights of the medium and large widgets, in points, by the screen's
// height in points, from Apple's widget size guidelines. A screen not listed
// takes the nearest one below it, which only ever leaves a row unused.
const WIDGET_HEIGHTS = [
	[956, { medium: 170, large: 382 }],
	[932, { medium: 170, large: 382 }],
	[926, { medium: 170, large: 382 }],
	[896, { medium: 169, large: 379 }],
	[874, { medium: 158, large: 354 }],
	[852, { medium: 158, large: 354 }],
	[844, { medium: 158, large: 354 }],
	[812, { medium: 155, large: 345 }],
	[736, { medium: 157, large: 357 }],
	[667, { medium: 148, large: 324 }],
	[0, { medium: 148, large: 324 }],
];

/**
 * Return the height of a medium or large widget on this iPhone.
 *
 * @param {string} size "medium" or "large".
 * @returns {number} The height, in points.
 */
function widgetHeight(size) {
	requireMember(size, ["medium", "large"], "size");
	const screen = Device.screenSize();
	const tall = Math.max(screen.width, screen.height);
	const match = WIDGET_HEIGHTS.find(([height]) => tall >= height);
	return match[1][size];
}

/**
 * Return how many rows fit in a widget with the same padding on every side.
 *
 * @param {number} height The widget's height, in points.
 * @param {number} sections How many services' headings it shows.
 * @returns {number} The most rows that fit.
 */
function capacity(height, sections) {
	requireType(height, "number", "height");
	requireType(sections, "number", "sections");
	const inner = height - 2 * LAYOUT.padding - sections * (LAYOUT.heading + LAYOUT.headingGap) - (sections - 1) * LAYOUT.sectionGap;
	// The last row of each section has no gap under it.
	return Math.max(1, Math.floor((inner + sections * LAYOUT.rowGap) / (LAYOUT.row + LAYOUT.rowGap)));
}

/**
 * Return the usages a size shows when its widget has no Parameter.
 *
 * @param {string} size A key of SIZES.
 * @param {object} readings From readAll.
 * @returns {string[]} The choices, as service/usage.
 */
function defaultChoice(size, readings) {
	requireMember(size, Object.keys(SIZES), "size");
	const signedIn = SERVICE_KEYS.filter(key => readings[key] && readings[key].signedIn);
	const first = signedIn[0] || CLAUDE;
	if (size === "large") {
		return (signedIn.length ? signedIn : [first]).flatMap(key => [`${key}/${SESSION}`, `${key}/${WEEKLY}`]);
	}
	if (size === "medium") {
		return [`${first}/${SESSION}`, `${first}/${WEEKLY}`];
	}
	return [`${first}/${SESSION}`];
}

/**
 * Return the usages one size shows of a list, in the order it shows them.
 *
 * A size with room for one usage shows the first. The medium widget shows one
 * service, the first one's, up to where the list moves to another. The large
 * widget shows every service, each where it first appears, with its own usages
 * in the order they were listed. Neither takes more rows than fit with the same
 * padding on every side.
 *
 * @param {string} size A key of SIZES.
 * @param {string[]} choice As service/usage.
 * @returns {string[]} The usages to show.
 */
function arrange(size, choice) {
	requireMember(size, Object.keys(SIZES), "size");
	requireType(choice, "array", "choice");
	// A usage listed twice is shown once, where it is first listed.
	choice = choice.filter((id, index) => choice.indexOf(id) === index);
	if (!choice.length) {
		return [];
	}
	const serviceOf = id => id.split("/")[0];
	if (size === "medium") {
		const first = serviceOf(choice[0]);
		const run = [];
		for (const id of choice) {
			if (serviceOf(id) !== first) {
				break;
			}
			run.push(id);
		}
		return run.slice(0, capacity(widgetHeight("medium"), 1));
	}
	if (size === "large") {
		const order = [];
		const groups = {};
		for (const id of choice) {
			const service = serviceOf(id);
			if (!groups[service]) {
				groups[service] = [];
				order.push(service);
			}
			if (!groups[service].includes(id)) {
				groups[service].push(id);
			}
		}
		const room = capacity(widgetHeight("large"), order.length);
		const shown = [];
		for (const service of order) {
			for (const id of groups[service]) {
				if (shown.length < room) {
					shown.push(id);
				}
			}
		}
		return shown;
	}
	return [choice[0]];
}

/**
 * Return what one widget shows: its Parameter, else what its size shows by default.
 *
 * @param {string} size A key of SIZES.
 * @param {string} parameter The widget's Parameter, empty when none was set.
 * @param {object} readings From readAll.
 * @returns {string[]} The choices, as service/usage, arranged for the size.
 */
function choiceFor(size, parameter, readings) {
	requireMember(size, Object.keys(SIZES), "size");
	requireType(parameter, "string", "parameter");
	const fromParameter = parameter.split(",").map(part => part.trim().toLowerCase()).filter(part => SERVICE_KEYS.includes(part.split("/")[0]) && part.includes("/"));
	return arrange(size, fromParameter.length ? fromParameter : defaultChoice(size, readings));
}

/**
 * Return the rows a choice stands for, with their readings.
 *
 * @param {string[]} choice As service/usage.
 * @param {object} readings From readAll.
 * @returns {Array<{service: string, key: string, label: string, percent: number|null}>} The rows, in the order given.
 */
function rowsFor(choice, readings) {
	requireType(choice, "array", "choice");
	return choice.map(id => {
		const [service, key] = id.split("/");
		const reading = readings[service] || { usages: [] };
		const usage = reading.usages.find(entry => entry.key === key);
		const fallback = key === SESSION ? "Current session" : key === WEEKLY ? "This week" : key;
		return { service, key, label: usage ? usage.label : fallback, percent: usage ? usage.percent : null };
	});
}

// Drawing ---------------------------------------------------------------------

/**
 * Return the colors widgets are drawn in, for the background chosen in the settings.
 *
 * @returns {{dark: boolean, background: Color, text: Color, secondary: Color}} The colors.
 */
function look() {
	const background = readJSON(SETTINGS_PATH, {}).background;
	const dark = (BACKGROUNDS.includes(background) ? background : DEFAULT_BACKGROUND) === "black";
	return {
		dark,
		background: new Color(dark ? "#000000" : "#ffffff"),
		text: new Color(dark ? "#ffffff" : "#000000"),
		secondary: new Color(dark ? "#98989d" : "#6e6e73"),
	};
}

/**
 * Return a service's accent, as it reads on a background.
 *
 * @param {string} service CLAUDE or CHATGPT.
 * @param {boolean} dark Whether the background is black.
 * @returns {Color} Claude's orange, or for ChatGPT, whose mark is monochrome, the text color.
 */
function accentOf(service, dark) {
	requireMember(service, SERVICE_KEYS, "service");
	requireType(dark, "boolean", "dark");
	if (service === CLAUDE) {
		return new Color("#d97757");
	}
	return new Color(dark ? "#ffffff" : "#000000");
}

/**
 * Return a service's mark, in its own color on a background.
 *
 * @param {string} service CLAUDE or CHATGPT.
 * @param {boolean} dark Whether the background is black.
 * @returns {Image} The mark.
 */
function markImage(service, dark) {
	requireMember(service, SERVICE_KEYS, "service");
	requireType(dark, "boolean", "dark");
	const data = service === CLAUDE ? MARKS.claude : dark ? MARKS.chatgptWhite : MARKS.chatgptBlack;
	return Image.fromData(Data.fromBase64String(data));
}

/**
 * Return the ramp color of a usage share.
 *
 * @param {number} percent The share, 0 to 100.
 * @param {number} alpha The opacity, 0 to 1.
 * @returns {Color} The color.
 */
function usageColor(percent, alpha) {
	requireType(percent, "number", "percent");
	requireType(alpha, "number", "alpha");
	const value = clampPercent(percent);
	let previous = USAGE_RAMP[0];
	for (const stop of USAGE_RAMP) {
		if (value <= stop[0]) {
			const span = stop[0] - previous[0];
			const ratio = span <= 0 ? 0 : (value - previous[0]) / span;
			const channel = index => Math.round(previous[1][index] + (stop[1][index] - previous[1][index]) * ratio);
			const hex = [0, 1, 2].map(index => channel(index).toString(16).padStart(2, "0")).join("");
			return new Color(`#${hex}`, alpha);
		}
		previous = stop;
	}
	return new Color("#ff453a", alpha);
}

/**
 * Return the outline of a stretch of the dial's band, round at both ends.
 *
 * The band is one closed shape, filled once, rather than a stroked line with a
 * dot at each end: Scriptable's lines have square ends, and a dot laid over a
 * translucent line doubles its color where they overlap.
 *
 * @param {number} edge The dial's square, in points.
 * @param {object} geometry DIAL or LOCK_DIAL.
 * @param {number} fraction How much of the sweep, 0 to 1.
 * @returns {Path} The band's outline.
 */
function bandPath(edge, geometry, fraction) {
	requireType(edge, "number", "edge");
	requireType(geometry, "object", "geometry");
	requireType(fraction, "number", "fraction");
	const center = edge / 2;
	const radius = edge * geometry.radius;
	const half = (edge * geometry.stroke) / 2;
	const toRadians = degrees => (degrees * Math.PI) / 180;
	const from = geometry.start;
	const to = geometry.start + geometry.sweep * fraction;
	const steps = Math.max(8, Math.round(120 * fraction));
	const capSteps = 16;
	const points = [];
	const onCircle = (cx, cy, r, degrees) => new Point(cx + r * Math.cos(toRadians(degrees)), cy + r * Math.sin(toRadians(degrees)));
	for (let step = 0; step <= steps; step++) {
		points.push(onCircle(center, center, radius + half, from + ((to - from) * step) / steps));
	}
	const end = onCircle(center, center, radius, to);
	for (let step = 1; step < capSteps; step++) {
		points.push(onCircle(end.x, end.y, half, to + (180 * step) / capSteps));
	}
	for (let step = steps; step >= 0; step--) {
		points.push(onCircle(center, center, radius - half, from + ((to - from) * step) / steps));
	}
	const start = onCircle(center, center, radius, from);
	for (let step = 1; step < capSteps; step++) {
		points.push(onCircle(start.x, start.y, half, from + 180 + (180 * step) / capSteps));
	}
	const path = new Path();
	path.addLines(points);
	path.closeSubpath();
	return path;
}

/**
 * Return the dial of one usage: the share inside an open arc, the mark in its gap.
 *
 * @param {string} service CLAUDE or CHATGPT.
 * @param {number|null} percent The share, or null before a reading.
 * @param {number} edge The square to draw, in points.
 * @param {object} geometry DIAL or LOCK_DIAL.
 * @param {object} colors From look(); the lock screen dial passes white on black.
 * @returns {Image} The dial.
 */
function dialImage(service, percent, edge, geometry, colors) {
	requireMember(service, SERVICE_KEYS, "service");
	requireType(edge, "number", "edge");
	requireType(colors, "object", "colors");
	const accent = geometry === LOCK_DIAL ? colors.text : accentOf(service, colors.dark);
	const context = new DrawContext();
	context.size = new Size(edge, edge);
	context.opaque = false;
	context.respectScreenScale = true;

	context.addPath(bandPath(edge, geometry, 1));
	context.setFillColor(new Color(accent.hex, TRACK_OPACITY));
	context.fillPath();
	if (percent !== null && percent > 0) {
		context.addPath(bandPath(edge, geometry, clampPercent(percent) / 100));
		context.setFillColor(accent);
		context.fillPath();
	}

	context.setTextColor(colors.text);
	context.setFont(Font.semiboldRoundedSystemFont(edge * geometry.number));
	context.setTextAlignedCenter();
	const text = percent === null ? "-" : String(Math.round(clampPercent(percent)));
	const textHeight = edge * geometry.number * 1.25;
	context.drawTextInRect(text, new Rect(0, (edge - textHeight) / 2, edge, textHeight));
	const mark = edge * geometry.markSize;
	context.drawImageInRect(markImage(service, colors.dark), new Rect((edge - mark) / 2, edge * geometry.markCenterY - mark / 2, mark, mark));
	return context.getImage();
}

/**
 * Return a usage bar: a capsule filled from the left, in the usage ramp.
 *
 * @param {number|null} percent The share, or null before a reading.
 * @param {number} width The bar's width, in points.
 * @param {number} height The bar's height, in points.
 * @param {boolean} monochrome Whether to draw in white for the lock screen.
 * @returns {Image} The bar.
 */
function barImage(percent, width, height, monochrome) {
	requireType(width, "number", "width");
	requireType(height, "number", "height");
	requireType(monochrome, "boolean", "monochrome");
	const context = new DrawContext();
	context.size = new Size(width, height);
	context.opaque = false;
	context.respectScreenScale = true;
	const value = percent === null ? 0 : clampPercent(percent);
	const track = monochrome ? new Color("#ffffff", 0.3) : percent === null ? new Color("#8e8e93", 0.25) : usageColor(value, TRACK_OPACITY);
	const fill = monochrome ? new Color("#ffffff") : usageColor(value, 1);
	const trackPath = new Path();
	trackPath.addRoundedRect(new Rect(0, 0, width, height), height / 2, height / 2);
	context.addPath(trackPath);
	context.setFillColor(track);
	context.fillPath();
	const filled = (width * value) / 100;
	if (filled > 0) {
		const fillPath = new Path();
		fillPath.addRoundedRect(new Rect(0, 0, Math.max(height, filled), height), height / 2, height / 2);
		context.addPath(fillPath);
		context.setFillColor(fill);
		context.fillPath();
	}
	return context.getImage();
}

/**
 * Return a bar with its share beside it, as one image of a fixed width.
 *
 * Drawn together because a widget does not keep a column of text at a fixed
 * width: a narrow number would let its bar grow, and bars in different widgets
 * would end in different places.
 *
 * @param {number|null} percent The share, or null before a reading.
 * @param {object} metrics The bar's width and height, the share column's width, the font size, the
 *     colors, and the height of the row it sits in, if any.
 * @returns {{image: Image, width: number, height: number}} The image and its size, in points.
 */
function meterImage(percent, metrics) {
	requireType(metrics, "object", "metrics");
	const width = metrics.barWidth + metrics.valueWidth;
	// As tall as the row it sits in, where it has one, so it adds nothing to the
	// height the row limits were worked out with.
	const height = metrics.rowHeight || Math.ceil(metrics.font * 1.4);
	const context = new DrawContext();
	context.size = new Size(width, height);
	context.opaque = false;
	context.respectScreenScale = true;
	context.drawImageInRect(
		barImage(percent, metrics.barWidth, metrics.barHeight, metrics.monochrome),
		new Rect(0, (height - metrics.barHeight) / 2, metrics.barWidth, metrics.barHeight)
	);
	context.setFont(Font.semiboldMonospacedSystemFont(metrics.font));
	context.setTextColor(metrics.colors.text);
	context.setTextAlignedRight();
	const line = metrics.font * 1.25;
	context.drawTextInRect(percentText(percent), new Rect(metrics.barWidth, (height - line) / 2, metrics.valueWidth, line));
	return { image: context.getImage(), width, height };
}

/**
 * Return the share as the widgets print it.
 *
 * @param {number|null} percent The share, or null before a reading.
 * @returns {string} Such as "23%", or "-" before a reading.
 */
function percentText(percent) {
	return percent === null ? "-" : `${Math.round(clampPercent(percent))}%`;
}

// Widgets ---------------------------------------------------------------------

// The lock screen draws in one tone of its own, so its widgets are drawn white
// on nothing and iOS tints them.
const LOCK_COLORS = { dark: true, text: new Color("#ffffff"), secondary: new Color("#ffffff", 0.7) };

// The lock screen rectangle is about 155 points wide on the narrowest iPhone:
// the bar and the share column together stay inside that.
const LOCK_BAR_WIDTH = 96;
const LOCK_VALUE_WIDTH = 48;

// The rows of the medium and large widgets, the same in both. The share sits in
// a column of its own, wide enough for "100%", so every bar ends at the same
// place whatever the number beside it, as in the desktop panels.
const ROW_METRICS = { font: 13, barWidth: 110, barHeight: 5, valueWidth: 42, rowHeight: LAYOUT.row, monochrome: false };

/**
 * Return the small widget, or the lock screen circular one: one usage, as a dial.
 *
 * @param {object} row The usage, from rowsFor.
 * @param {boolean} accessory Whether this is the lock screen widget.
 * @returns {ListWidget} The widget.
 */
function dialWidget(row, accessory) {
	requireType(row, "object", "row");
	requireType(accessory, "boolean", "accessory");
	const widget = new ListWidget();
	const colors = accessory ? LOCK_COLORS : look();
	if (!accessory) {
		widget.backgroundColor = colors.background;
	}
	const padding = accessory ? 0 : 8;
	widget.setPadding(padding, padding, padding, padding);
	const stack = widget.addStack();
	stack.addSpacer();
	const edge = accessory ? 76 : 140;
	const image = stack.addImage(dialImage(row.service, row.percent, edge, accessory ? LOCK_DIAL : DIAL, colors));
	image.imageSize = new Size(edge, edge);
	stack.addSpacer();
	return widget;
}

/**
 * Add one row: the usage's name, its bar and its share.
 *
 * @param {WidgetStack|ListWidget} parent Where to add it.
 * @param {object} row The usage, from rowsFor.
 * @param {object} metrics The font size, the bar size and the colors.
 * @returns {void}
 */
function addRow(parent, row, metrics) {
	requireType(row, "object", "row");
	requireType(metrics, "object", "metrics");
	const line = parent.addStack();
	line.layoutHorizontally();
	line.centerAlignContent();
	line.size = new Size(0, LAYOUT.row);
	const name = line.addText(row.label);
	name.font = Font.systemFont(metrics.font);
	name.textColor = metrics.colors.text;
	name.lineLimit = 1;
	line.addSpacer(6);
	line.addSpacer();
	const meter = meterImage(row.percent, metrics);
	const image = line.addImage(meter.image);
	image.imageSize = new Size(meter.width, meter.height);
}

/**
 * Add a service's heading: its mark and its name.
 *
 * @param {WidgetStack|ListWidget} parent Where to add it.
 * @param {string} service CLAUDE or CHATGPT.
 * @param {object} colors From look().
 * @returns {void}
 */
function addHeading(parent, service, colors) {
	requireMember(service, SERVICE_KEYS, "service");
	requireType(colors, "object", "colors");
	const heading = parent.addStack();
	heading.layoutHorizontally();
	heading.centerAlignContent();
	heading.size = new Size(0, LAYOUT.heading);
	const mark = heading.addImage(markImage(service, colors.dark));
	mark.imageSize = new Size(LAYOUT.heading, LAYOUT.heading);
	heading.addSpacer(8);
	const title = heading.addText(SERVICES[service].label);
	title.font = Font.semiboldSystemFont(13);
	title.textColor = colors.text;
}

/**
 * Return the medium or large widget: the usages as bars, under each service's heading.
 *
 * The content starts at the top, so its first line is the same distance from
 * the edge in every widget, whatever it holds, as the Mac widget's is.
 *
 * @param {Array} rows The usages, from rowsFor, already arranged for the size.
 * @param {object} readings From readAll, for the message of a service nobody is signed in to.
 * @returns {ListWidget} The widget.
 */
function barsWidget(rows, readings) {
	requireType(rows, "array", "rows");
	requireType(readings, "object", "readings");
	const colors = look();
	const metrics = Object.assign({ colors }, ROW_METRICS);
	const widget = new ListWidget();
	widget.backgroundColor = colors.background;
	widget.setPadding(LAYOUT.padding, LAYOUT.padding, LAYOUT.padding, LAYOUT.padding);
	let current = "";
	let inSection = 0;
	for (const row of rows) {
		const signedIn = readings[row.service] && readings[row.service].signedIn;
		if (row.service !== current) {
			if (current) {
				widget.addSpacer(LAYOUT.sectionGap);
			}
			current = row.service;
			inSection = 0;
			addHeading(widget, row.service, colors);
			widget.addSpacer(LAYOUT.headingGap);
			if (!signedIn) {
				const note = widget.addText("Run FORL in Scriptable to sign in.");
				note.font = Font.systemFont(12);
				note.textColor = colors.secondary;
			}
		}
		if (signedIn) {
			if (inSection) {
				widget.addSpacer(LAYOUT.rowGap);
			}
			addRow(widget, row, metrics);
			inSection++;
		}
	}
	widget.addSpacer();
	return widget;
}

/**
 * Return the lock screen rectangular widget: one usage, its mark and name over its bar and share.
 *
 * The bar takes what is left beside a share column wide enough for "100%", so
 * the number is never cut short on the narrowest lock screen.
 *
 * @param {object} row The usage, from rowsFor.
 * @returns {ListWidget} The widget.
 */
function rectangularWidget(row) {
	requireType(row, "object", "row");
	const widget = new ListWidget();
	widget.setPadding(0, 0, 0, 0);
	widget.addSpacer();

	const heading = widget.addStack();
	heading.layoutHorizontally();
	heading.centerAlignContent();
	const mark = heading.addImage(markImage(row.service, true));
	mark.imageSize = new Size(15, 15);
	heading.addSpacer(6);
	const name = heading.addText(row.label);
	name.font = Font.semiboldSystemFont(15);
	name.textColor = LOCK_COLORS.text;
	name.lineLimit = 1;
	name.minimumScaleFactor = 0.8;
	heading.addSpacer();

	widget.addSpacer(6);
	const meter = meterImage(row.percent, {
		barWidth: LOCK_BAR_WIDTH,
		barHeight: 8,
		valueWidth: LOCK_VALUE_WIDTH,
		font: 14,
		monochrome: true,
		colors: LOCK_COLORS,
	});
	const image = widget.addImage(meter.image);
	image.imageSize = new Size(meter.width, meter.height);
	widget.addSpacer();
	return widget;
}

/**
 * Return the lock screen inline widget: one usage on one line, such as "Claude 23%".
 *
 * @param {object} row The usage, from rowsFor.
 * @returns {ListWidget} The widget.
 */
function inlineWidget(row) {
	requireType(row, "object", "row");
	const widget = new ListWidget();
	widget.addText(`${SERVICES[row.service].label} ${percentText(row.percent)}`);
	return widget;
}

/**
 * Build the widget for the size iOS is drawing.
 *
 * @param {string} family What config.widgetFamily reports.
 * @param {string} parameter The widget's Parameter.
 * @returns {Promise<ListWidget>} The widget.
 */
async function buildWidget(family, parameter) {
	requireType(family, "string", "family");
	requireType(parameter, "string", "parameter");
	const readings = await readAll();
	const size = family === "extraLarge" ? "large" : family in SIZES ? family : "medium";
	const rows = rowsFor(choiceFor(size, parameter, readings), readings);
	let widget;
	if (size === "small" || size === "accessoryCircular") {
		widget = dialWidget(rows[0], size === "accessoryCircular");
	} else if (size === "accessoryRectangular") {
		widget = rectangularWidget(rows[0]);
	} else if (size === "accessoryInline") {
		widget = inlineWidget(rows[0]);
	} else {
		widget = barsWidget(rows, readings);
	}
	widget.refreshAfterDate = new Date(Date.now() + REFRESH_MINUTES * 60 * 1000);
	widget.url = URLScheme.forRunningScript();
	return widget;
}

// Settings --------------------------------------------------------------------

/**
 * Show a message with one button.
 *
 * @param {string} title The heading.
 * @param {string} message The text under it.
 * @returns {Promise<void>}
 */
async function tell(title, message) {
	requireType(title, "string", "title");
	requireType(message, "string", "message");
	const alert = new Alert();
	alert.title = title;
	alert.message = message;
	alert.addAction("OK");
	await alert.presentAlert();
}

/**
 * Add an empty row, which is how a table is given space between its sections.
 *
 * @param {UITable} table The table.
 * @param {number} height The space, in points.
 * @returns {void}
 */
function addGap(table, height) {
	requireType(height, "number", "height");
	const gap = new UITableRow();
	gap.height = height;
	table.addRow(gap);
}

/**
 * Add a section heading to a table.
 *
 * @param {UITable} table The table.
 * @param {string} title The heading.
 * @returns {void}
 */
function addHeader(table, title) {
	requireType(title, "string", "title");
	const row = new UITableRow();
	row.isHeader = true;
	row.addText(title);
	table.addRow(row);
}

/**
 * Add a row with a name, a line under it, and a word that acts on it.
 *
 * The name takes most of the width, so it is not cut short beside the word.
 *
 * @param {UITable} table The table.
 * @param {string} title The name.
 * @param {string} detail The line under it.
 * @param {string} label The word, such as "Sign in".
 * @param {Function} onSelect Called when the row is tapped.
 * @returns {void}
 */
function addAction(table, title, detail, label, onSelect) {
	requireType(title, "string", "title");
	requireType(onSelect, "function", "onSelect");
	const row = new UITableRow();
	row.height = 60;
	const text = row.addText(title, detail);
	text.widthWeight = 75;
	const button = row.addText(label);
	button.widthWeight = 25;
	button.rightAligned();
	button.titleColor = Color.blue();
	row.dismissOnSelect = false;
	row.onSelect = onSelect;
	table.addRow(row);
}

/**
 * Show the settings: the accounts, then what the widgets show and on what.
 *
 * @returns {Promise<void>}
 */
async function showSettings() {
	const table = new UITable();
	table.showSeparators = true;
	let readings = await readAll();

	const render = () => {
		table.removeAllRows();
		addHeader(table, "Accounts");
		for (const key of SERVICE_KEYS) {
			const tokens = loadTokens(key);
			const reading = readings[key];
			const detail = tokens ? (tokens.account || "Signed in") + (reading.error ? ` (${reading.error})` : "") : "Not signed in";
			addAction(table, SERVICES[key].label, detail, tokens ? "Sign out" : "Sign in", async () => {
				try {
					await toggleAccount(key);
				} catch (error) {
					await tell("Sign-in failed", String(error.message || error));
				}
				readings = await readAll();
				render();
			});
		}

		addGap(table, 36);
		addHeader(table, "Widgets");
		const settings = readJSON(SETTINGS_PATH, {});
		const background = BACKGROUNDS.includes(settings.background) ? settings.background : DEFAULT_BACKGROUND;
		addAction(table, "Background", background === "black" ? "Black" : "White", "Change", () => {
			settings.background = background === "black" ? "white" : "black";
			writeJSON(SETTINGS_PATH, settings);
			render();
		});
		addAction(table, "Usages", "Choose what a widget shows", "Choose", async () => {
			await makeParameter(readings);
		});
		table.reload();
	};

	render();
	await table.present();
}

/**
 * Sign in to a service, or sign out of it.
 *
 * @param {string} serviceKey CLAUDE or CHATGPT.
 * @returns {Promise<void>}
 */
async function toggleAccount(serviceKey) {
	requireMember(serviceKey, SERVICE_KEYS, "serviceKey");
	if (!loadTokens(serviceKey)) {
		await signInInSafari(serviceKey);
		return;
	}
	const confirm = new Alert();
	confirm.title = `Sign out of ${SERVICES[serviceKey].label}?`;
	confirm.addDestructiveAction("Sign out");
	confirm.addCancelAction("Cancel");
	if ((await confirm.presentAlert()) === 0) {
		saveTokens(serviceKey, null);
	}
}

/**
 * Let the user tick usages, and copy the widget Parameter that shows them.
 *
 * Every usage of both services is listed, numbered in the order ticked. A
 * small or lock screen widget shows the first; the medium one the first
 * service's; the large one all of them, as many as fit.
 *
 * @param {object} readings From readAll, which names the usages there are.
 * @returns {Promise<void>}
 */
async function makeParameter(readings) {
	requireType(readings, "object", "readings");
	let chosen = [];
	const table = new UITable();
	table.showSeparators = true;

	const render = () => {
		table.removeAllRows();
		SERVICE_KEYS.forEach((key, index) => {
			if (index) {
				addGap(table, 36);
			}
			addHeader(table, SERVICES[key].label);
			const reading = readings[key];
			const usages = reading && reading.usages.length
				? reading.usages
				: [{ key: SESSION, label: "Current session" }, { key: WEEKLY, label: "This week" }];
			for (const usage of usages) {
				const id = `${key}/${usage.key}`;
				const row = new UITableRow();
				row.height = 48;
				const name = row.addText(usage.label);
				name.widthWeight = 85;
				const position = chosen.indexOf(id);
				const tick = row.addText(position >= 0 ? `${position + 1}` : "");
				tick.widthWeight = 15;
				tick.rightAligned();
				tick.titleColor = Color.blue();
				row.dismissOnSelect = false;
				row.onSelect = () => {
					chosen = position >= 0 ? chosen.filter(entry => entry !== id) : chosen.concat(id);
					render();
				};
				table.addRow(row);
			}
		});
		if (chosen.length) {
			addGap(table, 36);
			// A full width bar in the system blue, which is as much of a button
			// as a table row can be made into.
			const row = new UITableRow();
			row.height = 64;
			row.backgroundColor = new Color("#0a84ff");
			row.dismissOnSelect = false;
			const label = row.addText("Copy the Parameter", `${chosen.length} ${chosen.length === 1 ? "usage" : "usages"} ticked`);
			label.centerAligned();
			label.titleFont = Font.boldSystemFont(17);
			label.titleColor = Color.white();
			label.subtitleFont = Font.systemFont(13);
			label.subtitleColor = new Color("#ffffff", 0.8);
			row.onSelect = async () => {
				Pasteboard.copy(chosen.join(", "));
				await tell("Copied", "Touch and hold the widget, choose Edit Widget, and paste it into Parameter.");
			};
			table.addRow(row);
		}
		table.reload();
	};

	render();
	await table.present();
}

// Run -------------------------------------------------------------------------

if (config.runsInWidget || config.runsInAccessoryWidget) {
	Script.setWidget(await buildWidget(config.widgetFamily || "medium", args.widgetParameter || ""));
} else {
	await showSettings();
}
Script.complete();
