import { Request, Response } from "express";

class TokenValidator {
  validate(token: string, strict: boolean = false): boolean {
    return this.checkFormat(token);
  }

  checkFormat(token: string): boolean {
    return token.length > 0;
  }
}

function verifyRequest(req: Request, res: Response): void {
  const validator = new TokenValidator();
  validator.validate("abc", true);
}
