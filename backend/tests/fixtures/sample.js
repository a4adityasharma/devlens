import { fetchUser } from "./api";

function generateToken(username) {
  return username;
}

class AuthService {
  login(username, password) {
    const token = generateToken(username);
    return this.validate(token);
  }

  validate(token) {
    return true;
  }
}

function refreshToken(token) {
  return token;
}

const logout = (sessionId) => {
  const svc = new AuthService();
  svc.login("a", "b");
  return null;
};
