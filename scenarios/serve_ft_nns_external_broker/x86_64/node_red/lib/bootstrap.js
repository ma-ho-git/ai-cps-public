"use strict";

const fs = require("node:fs");

function loadJson(path) {
  return JSON.parse(fs.readFileSync(path, "utf8"));
}

function loadJsonLines(path) {
  return fs
    .readFileSync(path, "utf8")
    .split(/\r?\n/)
    .filter((line) => line.trim().length > 0)
    .map((line) => JSON.parse(line));
}

module.exports = { loadJson, loadJsonLines };
