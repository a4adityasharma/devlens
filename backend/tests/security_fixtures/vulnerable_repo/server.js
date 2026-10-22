const { exec } = require('child_process');

function runTask(userInput) {
  exec(userInput, (err, stdout) => {
    console.log(stdout);
  });
}

function parseData(raw) {
  return eval(raw);
}

const secretKey = "sk-verysecrettoken12345";

function safeAdd(a, b) {
  return a + b;
}
