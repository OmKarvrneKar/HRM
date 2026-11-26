import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { Shield, KeyRound, User, Lock, RefreshCw, AlertCircle, CheckCircle2 } from 'lucide-react';
import { authApi } from '../../services/api/authApi';
import { useAuth } from '../../hooks/useAuth';

export const LoginPage = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { login } = useAuth();

  const [activeTab, setActiveTab] = useState('employee'); // 'employee' or 'hr'
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [captchaInput, setCaptchaInput] = useState('');
  const [captchaSvg, setCaptchaSvg] = useState('');
  const [captchaId, setCaptchaId] = useState('');
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  // Refresh CAPTCHA
  const refreshCaptcha = async () => {
    try {
      const data = await authApi.getCaptcha();
      if (data && (data.image || data.image_url || data.svg)) {
        setCaptchaSvg(data.image || data.image_url || data.svg);
      }
      if (data && data.captcha_id) {
        setCaptchaId(data.captcha_id);
      }
    } catch (e) {
      console.warn('Failed to load captcha:', e);
    }
  };

  useEffect(() => {
    refreshCaptcha();
    const params = new URLSearchParams(location.search);
    if (params.get('activated') === '1') {
      setSuccessMsg('Account successfully activated! Please log in with your credentials.');
    }
    if (params.get('session_expired') === '1') {
      setErrorMsg('Your session has expired. Please sign in again.');
    }
  }, [location.search]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMsg('');
    setSuccessMsg('');

    if (!identifier.trim() || !password.trim()) {
      setErrorMsg('Please enter both employee ID / email and password.');
      return;
    }

    try {
      setLoading(true);
      const payload = {
        identifier: identifier.trim(),
        username: identifier.trim(),
        employee_id: identifier.trim(),
        password: password,
        portal_type: activeTab,
      };
      if (captchaInput.trim() && captchaId) {
        payload.captcha_id = captchaId;
        payload.captcha_answer = captchaInput.trim();
      }
      await login(payload);
      navigate('/dashboard', { replace: true });
    } catch (err) {
      setErrorMsg(
        err.response?.data?.message ||
        err.response?.data?.error ||
        err.message ||
        'Authentication failed. Please check your credentials.'
      );
      refreshCaptcha();
      setCaptchaInput('');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-indigo-950 flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-2xl border border-slate-100 overflow-hidden">
        {/* Top Header */}
        <div className="bg-gradient-to-r from-blue-700 to-indigo-800 p-6 text-white text-center">
          <div className="inline-flex h-12 w-12 rounded-xl bg-white/10 backdrop-blur-md items-center justify-center font-extrabold text-xl mb-3 shadow-inner">
            AS
          </div>
          <h2 className="text-xl font-bold tracking-tight">AI SAMRAT HRMS</h2>
          <p className="text-xs text-blue-100 mt-1">Enterprise Workforce Management Portal</p>
        </div>

        {/* Portal Type Tabs */}
        <div className="flex border-b border-slate-200">
          <button
            type="button"
            onClick={() => {
              setActiveTab('employee');
              setErrorMsg('');
            }}
            className={`flex-1 py-3 text-xs font-semibold uppercase tracking-wider text-center transition-colors ${
              activeTab === 'employee'
                ? 'border-b-2 border-blue-600 text-blue-700 bg-blue-50/50'
                : 'text-slate-500 hover:text-slate-800'
            }`}
          >
            Staff & Intern Portal
          </button>
          <button
            type="button"
            onClick={() => {
              setActiveTab('hr');
              setErrorMsg('');
            }}
            className={`flex-1 py-3 text-xs font-semibold uppercase tracking-wider text-center transition-colors ${
              activeTab === 'hr'
                ? 'border-b-2 border-blue-600 text-blue-700 bg-blue-50/50'
                : 'text-slate-500 hover:text-slate-800'
            }`}
          >
            Leadership / HR
          </button>
        </div>

        {/* Form Body */}
        <div className="p-6">
          {errorMsg && (
            <div className="mb-4 flex items-start gap-2.5 p-3 rounded-lg bg-rose-50 border border-rose-200 text-xs text-rose-700">
              <AlertCircle className="w-4 h-4 shrink-0 text-rose-500 mt-0.5" />
              <span>{errorMsg}</span>
            </div>
          )}

          {successMsg && (
            <div className="mb-4 flex items-start gap-2.5 p-3 rounded-lg bg-emerald-50 border border-emerald-200 text-xs text-emerald-700">
              <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-500 mt-0.5" />
              <span>{successMsg}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                {activeTab === 'employee' ? 'Employee ID or Official Email' : 'Leadership ID or Corporate Email'}
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                  <User className="w-4 h-4" />
                </div>
                <input
                  type="text"
                  value={identifier}
                  onChange={(e) => setIdentifier(e.target.value)}
                  placeholder={activeTab === 'employee' ? 'e.g. AS-1001 or email' : 'e.g. HR-1001 or MGR-1001'}
                  required
                  className="block w-full pl-9 pr-3 py-2 text-sm bg-slate-50 border border-slate-300 rounded-lg shadow-xs focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                />
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider">
                  Password
                </label>
                <Link
                  to="/activate"
                  className="text-xs text-blue-600 hover:text-blue-800 font-medium"
                >
                  Activate Account?
                </Link>
              </div>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                  <Lock className="w-4 h-4" />
                </div>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter your confidential password"
                  required
                  className="block w-full pl-9 pr-3 py-2 text-sm bg-slate-50 border border-slate-300 rounded-lg shadow-xs focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                />
              </div>
            </div>

            {/* Security CAPTCHA */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                Security Verification
              </label>
              <div className="flex items-center gap-3">
                <div className="h-10 px-2 bg-slate-100 border border-slate-200 rounded-lg flex items-center justify-center overflow-hidden shrink-0 select-none">
                  {captchaSvg ? (
                    <img src={captchaSvg} alt="Security CAPTCHA" className="h-8 object-contain select-none" />
                  ) : (
                    <span className="text-xs text-slate-400">Loading...</span>
                  )}
                </div>
                <button
                  type="button"
                  onClick={refreshCaptcha}
                  title="Refresh CAPTCHA"
                  className="p-2 text-slate-500 hover:text-slate-800 hover:bg-slate-100 rounded-lg border border-slate-200 transition"
                >
                  <RefreshCw className="w-4 h-4" />
                </button>
                <input
                  type="text"
                  value={captchaInput}
                  onChange={(e) => setCaptchaInput(e.target.value)}
                  placeholder="Code"
                  maxLength={6}
                  className="block w-full px-3 py-2 text-sm bg-slate-50 border border-slate-300 rounded-lg shadow-xs focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 uppercase tracking-widest font-mono font-semibold"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full mt-2 py-2.5 px-4 text-sm font-semibold text-white bg-blue-700 hover:bg-blue-800 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 rounded-lg shadow-md transition disabled:opacity-50"
            >
              {loading ? 'Authenticating...' : 'Sign In to Workforce'}
            </button>
          </form>

          <div className="mt-6 pt-4 border-t border-slate-100 text-center text-xs text-slate-500">
            <span>New joining intern? </span>
            <Link to="/activate" className="font-semibold text-blue-600 hover:text-blue-800">
              Activate your enterprise account
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
};

export default LoginPage;

