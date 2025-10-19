function updateStatus(response, status, xhr) {
  if( document.title === 'RMS_telemetry' ) {
    document.title = response['station_id'];
  }
  
  var sp = document.getElementById('station_id');
  if( sp != null ) {
    sp.innerHTML = response['station_id'];
    sp.classList.remove("loading");
  }
  
  sp = document.getElementById('capture_active');
  if( sp != null ) {
    if( response['capture']['running'] ) {
      sp.innerHTML = 'active with ' + response['detections']['n_star'].toString() + ' stars and ' + response['detections']['n_meteor'].toString() + ' meteors';
    } else {
      var tStart = new Date(response['capture']['next_start']);
      var tNow = new Date();
      var until = (tStart.getTime() - tNow.getTime()) / 1000;
      var h = Math.floor(until / 3600);
      var m = Math.floor(until / 60) % 60;
      var msg = 'waiting for next start in ';
      if( h > 0 ) {
        if( m > 45) {
          msg += 'about ' + (h+1).toString() + ' hr';
        } else if (m > 15) {
          msg += 'about ' + h.toString() + ' hr, 30 min';
        } else {
          msg += 'about ' + h.toString() + ' hr';
        }
      } else if( m > 1 ) {
        msg += 'about ' + m.toString() +' min';
      } else if( m >= 0 ) {
        msg += '&lt1 min';
      } else {
        msg = "finishing up";
      }
      
      sp.innerHTML = msg;
    }
    sp.classList.remove("loading");
  }
}

function updateLinks(response, status, xhr) {
  sta = response['station_id'];
  cc = sta.slice(0, 2);
  
  var last_week = new Date();
  last_week.setDate(last_week.getDate() - 7);
  var lw_str = last_week.getFullYear() + "-";
  lw_str += String(last_week.getMonth() + 1).padStart(2, '0') + "-";
  lw_str += String(last_week.getDate()).padStart(2, '0');
  
  var ln = document.getElementById('weblog');
  if( ln != null ) {
    ln.innerHTML = 'Weblog Entry <i class="icon-external-link"></i>';
    ln.href = "https://globalmeteornetwork.org/weblog/" + cc + "/" + sta + "/latest/";
    ln.classList.remove("loading");
  }
  
  ln = document.getElementById('recent_contrib');
  if( ln != null ) {
    ln.innerHTML = 'Recent Contributions <i class="icon-external-link"></i>';
    ln.href = "https://explore.globalmeteornetwork.org/gmn_data_store/participating_station?created_at__gte=" + lw_str + "&station_code__exact=" + sta + "&_sort_desc=created_at";
    ln.classList.remove("loading");
  }
  
  ln = document.getElementById('recent_enable');
  if( ln != null ) {
    ln.innerHTML = "Recently Enabled (" + response['station_id'] + " + One Other Station) <i class=\"icon-external-link\"></i>";
    ln.href = "https://explore.globalmeteornetwork.org/gmn_data_store/-/query?sql=SELECT+ps_summary.meteor_unique_trajectory_identifier%2C+REPLACE%28REPLACE%28ps_summary.stations%2C+%3Ap0%2C+%27%27%29%2C+%27%2C%27%2C+%27%27%29+as+other_station%2C+m.beginning_utc_time%2C+m.elev_deg%2C+m.latbeg_n_deg%2C+m.lonbeg_e_deg%2C+m.latend_n_deg%2C+m.lonend_e_deg%2C+m.htbeg_km%2C+m.htend_km%2C+m.duration_sec%2C+m.peak_absmag%2C+m.vgeo_km_s%2C+m.created_at+as+meteor_created_at%2C+m.updated_at+as+meteor_updated_at+FROM+%28+SELECT+meteor_unique_trajectory_identifier%2C+GROUP_CONCAT%28station_code%29+as+stations%2C+COUNT%28*%29+as+station_count%2C+MAX%28created_at%29+as+latest_created_at+FROM+participating_station+WHERE+meteor_unique_trajectory_identifier+IN+%28+SELECT+meteor_unique_trajectory_identifier+FROM+participating_station+WHERE+station_code+%3D+%3Ap0+%29+GROUP+BY+meteor_unique_trajectory_identifier+HAVING+COUNT%28DISTINCT+station_code%29+%3D+2+%29+ps_summary+JOIN+meteor+m+ON+ps_summary.meteor_unique_trajectory_identifier+%3D+m.unique_trajectory_identifier+ORDER+BY+ps_summary.latest_created_at+DESC+LIMIT+101%3B&p0=" + sta + "&p1=" + lw_str;
    ln.classList.remove("loading");
  }
}

function fetchLatest() {
  $.ajax({'url': '/latest',
          'success': function(response, status, xhr) {
            updateStatus(response, status, xhr);
            updateLinks(response, status, xhr);
            setTimeout(fetchLatest, 30000);
          },
          'error': function() {
            setTimeout(fetchLatest, 30000);
          }
         });
}

function updatePrevious(response, status, xhr) {
  var sp = document.getElementById('last_capture');
  if( sp != null ) {
    sp.innerHTML = response['capture']['started'];
    sp.classList.remove("loading");
  }
  
  var n_meteor = response['detections']['n_meteor_final'];
  
  var astr_ok = response['camera']['astrometry_good'];
  var phot_ok = response['camera']['photometry_good'];
  var jitr_ok = (response['camera']['jitter_quality'] > 0.95) ? true : false;
  var fits_ok = (response['camera']['fits_fill'] > 0.95) ? true : false;
  
  var all_ok = astr_ok && phot_ok && jitr_ok && fits_ok;
  var failures = [];
  if( !astr_ok ) {
    failures.push('astrometry failed');
  }
  if( !phot_ok ) {
    failures.push('photometry failed');
  }
  if( !jitr_ok ) {
    failures.push('jitter quality low');
  }
  if( !fits_ok ) {
    failures.push('FITS fill fraction low');
  }
  var msg = 'OK with ' + n_meteor.toString() + ' meteors';
  if( failures.length > 0 ) {
    msg = 'FAILED with ' + (failures.join(', '));
  }
  
  sp = document.getElementById('last_overall');
  if( sp != null ) {
    sp.innerHTML = msg;
    if( all_ok ) {
      sp.classList.remove('error');
      sp.classList.add('ok');
    } else {
      sp.classList.add('error');
      sp.classList.remove('ok');
    }
    sp.classList.remove('loading');
  }
}

function fetchPrevious() {
  $.ajax({'url': '/previous',
          'success': function(response, status, xhr) {
            updatePrevious(response, status, xhr);
            setTimeout(fetchPrevious, 900000);
          },
          'error': function() {
            setTimeout(fetchPrevious, 900000);
          }
         });
}

function updateHistory(response, status, xhr) {
  var contents = '';
  for (let idx = response.length - 1; idx >= 0; idx--) {
    var date = response[idx];
    var date_str = date.slice(0,4) + "-" + date.slice(4,6) + "-" + date.slice(6,8);
    var entry = date_str;
    entry += ' - <a href="/previous?date=' + date + '">Detailed Status</a>';
    entry += ' - <a href="/previous/details.html?date=' + date + '">Meteor Details</a>';
    entry += ' - <a href="/previous/image?date=' + date + '">Stacked Meteors Image</a><br />';
    contents += entry;
  }
  
  var dv = document.getElementById('history_listing');
  if( dv != null ) {
    dv.innerHTML = contents;
    dv.classList.remove('loading');
  }
}

function fetchHistory() {
  $.ajax({'url': '/previous/dates',
          'success': function(response, status, xhr) {
            updateHistory(response, status, xhr);
            setTimeout(fetchHistory, 900000);
          },
          'error': function() {
            setTimeout(fetchHistory, 900000);
          }
         });
}

const zhr_flux_re = /in the next 24 hrs<tspan x="\d+(\.\d+)?" dy="1em">​<\/tspan><tspan x="\d+(\.\d+)?" dy="1em">​<\/tspan><\/tspan>(?<zhr>\d+)<tspan x="\d+\.\d+" dy="1em">​<\/tspan><tspan>meteors\/hr/;
const zhr_updated_re = new RegExp(/<p><b>Last update:\s*<\/b>.*<br>(?<date>\d+-\d+-\d+ \d+:\d+:\d+ UTC).*<br>Solar longitude (?<long>\d+(\.\d+)?) deg/, 'ms');
    
function updateZHR(response, status, xhr) {
  var sp = document.getElementById('zhr_rate');
  if( sp != null ) {
    var mtch1 = response.match(zhr_flux_re);
    var mtch2 = response.match(zhr_updated_re);
    if( mtch1 != null && mtch2 != null ) {
      sp.innerHTML = mtch1.groups['zhr'] + 'meteros/hr';
      sp.classList.remove('loading');
      
      sp = document.getElementById('zhr_updated');
      if( sp != null ) {
        sp.innerHTML = mtch2.groups('date');
        sp.classList.remove('loading');
      }
    }
  }
}

function fetchZHR() {
  if( document.title !== 'RMS_telemetry' ) {
    $.ajax({'url': "https://globalmeteornetwork.org/flux/",
            'success': function(response, status, xhr) {
              updateZHR(response, status, xhr);
              setTimeout(fetchZHR, 4*3600*1000);
            },
            'error': function() {
              setTimeout(fetchZHR, 1*3600*1000);
            }
           });
  } else {
    setTimeout(fetchZHR, 5*1000);
  }
}

function updateMonthlyCount(response, status, xhr) {
  var sp = document.getElementById('monthly_count');
  if( sp != null && response.ok ) {
    sp.innerHTML = response['rows'][0]['COUNT(meteor_unique_trajectory_identifier)'];
    sp.classList.remove('loading');
  }
}

function fetchMonthlyCount() {
  var last_month = new Date();
  last_month.setMonth(last_month.getMonth() - 1);
  var lm_str = last_month.getFullYear() + "-";
  lm_str += String(last_month.getMonth() + 1).padStart(2, '0') + "-";
  lm_str += String(last_month.getDate()).padStart(2, '0');
  
  if( document.title !== 'RMS_telemetry' ) {
    $.ajax({'url': "https://explore.globalmeteornetwork.org/gmn_data_store/-/query.json?sql=select+station_code%2C+COUNT%28meteor_unique_trajectory_identifier%29+from+participating_station+where+%22station_code%22+%3D+%3Ap0+AND+created_at+%3E%3D+%3Ap1&p0=" + document.title + "&p1=" + lm_str,
            'success': function(response, status, xhr) {
              updateMonthlyCount(response, status, xhr);
              setTimeout(fetchMonthlyCount, 4*3600*1000);
            },
            'error': function() {
              setTimeout(fetchMonthlyCount, 1*3600*1000);
            }
           });
  } else {
    setTimeout(fetchMonthlyCount, 5*1000);
  }
}

function initializePage() {
  fetchLatest();
  fetchPrevious();
  fetchHistory();
  fetchZHR();
  fetchMonthlyCount();
}
