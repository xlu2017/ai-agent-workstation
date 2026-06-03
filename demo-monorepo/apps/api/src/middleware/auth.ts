import { Request, Response, NextFunction } from 'express'

export function authMiddleware(req: Request, _res: Response, next: NextFunction) {
  // Simple auth — in production this would validate JWT/session
  const token = req.headers.authorization?.replace('Bearer ', '')
  if (token) {
    (req as any).userId = 'user-1'
  }
  next()
}
