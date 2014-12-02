window.opener.postMessage({auth_code: window.location.href},
                          window.location.origin);
window.close();

