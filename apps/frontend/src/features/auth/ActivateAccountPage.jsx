import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { CheckCircle2, AlertCircle, ArrowLeft, KeyRound, Mail, UserCheck } from 'lucide-react';
import { authApi } from '../../services/api/authApi';

export const ActivateAccountPage = () => {
  const navigate = useNavigate();

  const [step, setStep] = useState(1); // 1: Request OTP, 2: Enter OTP & Set Password
  const [employeeId, setEmployeeId] = useState('');
  const [email, setEmail] = useState('');
  const [otp, setOtp] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  const handleRequestOtp = async (e) => {
    e.preventDefault();
    setErrorMsg('');
    setSuccessMsg('');

    if (!employeeId.trim() || !email.trim()) {
      setErrorMsg('Please enter both your Employee ID and registered corporate Email.');
      return;
    }

    try {
      setLoading(true);
      const res = await authApi.requestActivationOtp(employeeId.trim(), email.trim());
      setSuccessMsg(res.message || 'Verification OTP sent to your registered email.');
      setStep(2);
    } catch (err) {
      setErrorMsg(
        err.response?.data?.message ||
        err.response?.data?.error ||
        'Could not generate activation OTP. Please verify your details.'
      );
    } finally {
      setLoading(false);
    }
  };

  const handleCompleteActivation = async (e) => {
    e.preventDefault();
    setErrorMsg('');
    setSuccessMsg('');

    if (!otp.trim()) {
      setErrorMsg('Please enter the 6-digit OTP code.');
      return;
    }

    if (newPassword.length < 8) {
      setErrorMsg('Password must be at least 8 characters long.');
      return;
    }

    if (newPassword !== confirmPassword) {
      setErrorMsg('Passwords do not match.');
      return;
    }

    try {
      setLoading(true);
      await authApi.completeActivation({
        employee_id: employeeId.trim(),
        email: email.trim(),
        otp: otp.trim(),
        new_password: newPassword,
      });
      navigate('/login?activated=1');
    } catch (err) {
      setErrorMsg(
        err.response?.data?.message ||
        err.response?.data?.error ||
        'Activation failed. Please ensure the OTP code is correct and not expired.'
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-indigo-950 flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-2xl border border-slate-100 overflow-hidden">
        <div className="bg-gradient-to-r from-blue-700 to-indigo-800 p-6 text-white text-center">
          <div className="inline-flex h-12 w-12 rounded-xl bg-white/10 backdrop-blur-md items-center justify-center font-extrabold text-xl mb-3 shadow-inner">
            <UserCheck className="w-6 h-6" />
          </div>
          <h2 className="text-xl font-bold tracking-tight">Account Activation</h2>
          <p className="text-xs text-blue-100 mt-1">
            {step === 1 ? 'Step 1 of 2: Verify Your Identity' : 'Step 2 of 2: Set Your New Password'}
          </p>
        </div>

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

          {step === 1 ? (
            <form onSubmit={handleRequestOtp} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                  Employee ID (e.g. AS-1001)
                </label>
                <input
                  type="text"
                  value={employeeId}
                  onChange={(e) => setEmployeeId(e.target.value)}
                  placeholder="e.g. AS-1001"
                  required
                  className="block w-full px-3 py-2 text-sm bg-slate-50 border border-slate-300 rounded-lg shadow-xs focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 uppercase font-mono"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                  Registered Email Address
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="e.g. yourname@aisamrat.com"
                  required
                  className="block w-full px-3 py-2 text-sm bg-slate-50 border border-slate-300 rounded-lg shadow-xs focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-2.5 px-4 text-sm font-semibold text-white bg-blue-700 hover:bg-blue-800 rounded-lg shadow-md transition disabled:opacity-50"
              >
                {loading ? 'Sending Verification Code...' : 'Send Activation Code'}
              </button>
            </form>
          ) : (
            <form onSubmit={handleCompleteActivation} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                  6-Digit OTP Code
                </label>
                <input
                  type="text"
                  value={otp}
                  onChange={(e) => setOtp(e.target.value)}
                  placeholder="123456"
                  maxLength={6}
                  required
                  className="block w-full px-3 py-2 text-sm bg-slate-50 border border-slate-300 rounded-lg shadow-xs focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono tracking-widest text-center text-lg font-bold"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                  Set New Password
                </label>
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="Minimum 8 characters"
                  required
                  className="block w-full px-3 py-2 text-sm bg-slate-50 border border-slate-300 rounded-lg shadow-xs focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                  Confirm Password
                </label>
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Re-type new password"
                  required
                  className="block w-full px-3 py-2 text-sm bg-slate-50 border border-slate-300 rounded-lg shadow-xs focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setStep(1)}
                  className="py-2.5 px-3 text-xs font-semibold text-slate-600 bg-slate-100 hover:bg-slate-200 rounded-lg transition"
                >
                  Back
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  className="flex-1 py-2.5 px-4 text-sm font-semibold text-white bg-blue-700 hover:bg-blue-800 rounded-lg shadow-md transition disabled:opacity-50"
                >
                  {loading ? 'Activating...' : 'Set Password & Complete'}
                </button>
              </div>
            </form>
          )}

          <div className="mt-6 pt-4 border-t border-slate-100 text-center">
            <Link
              to="/login"
              className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-600 hover:text-blue-700"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              Return to Login
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ActivateAccountPage;

